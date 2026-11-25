import json
import os
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.auth_session import AuthSession
from app.models.notion_account import NotionAccount
from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.user import User
from app.services import external_sync, notion_oauth as service
from app.services.auth_service import authenticated_session, InvalidCredentialsError, utc_now
from app.routers.project_integrations import integrations
from app.routers.project_connections import connections
from scripts.setup_notion_accounts_db import setup
import test_dashboard_database
from test_external_sync import PAGE, NOTION


WORKSPACE = '12345678-1234-1234-1234-123456789abc'


class NotionOAuthTests(unittest.TestCase):
    def setUp(self):
        test_dashboard_database.DashboardDatabaseTests.setUp(self)
        self.env = patch.dict(os.environ, {
            'NOTION_CLIENT_ID': 'client', 'NOTION_CLIENT_SECRET': 'client-secret',
            'NOTION_OAUTH_REDIRECT_URI': 'http://localhost:5173/auth/notion/callback',
            'NOTION_TOKEN': 'legacy-secret', 'NOTION_TOKEN_OWNER_ID': '999',
            'NOTION_ALLOWED_PAGE_IDS': 'b' * 32,
        })
        self.env.start()
        # Mock only the encryption library boundary; exercise real DB and auth.
        self.encrypted = {}
        def encrypt(payload):
            ciphertext = f'opaque-{len(self.encrypted)}'.encode()
            self.encrypted[ciphertext.decode()] = json.loads(payload)
            return ciphertext
        self.encoder = Mock()
        self.encoder.encrypt.side_effect = encrypt
        self.cipher_patch = patch.object(service, 'cipher', return_value=self.encoder)
        self.cipher_patch.start()
        self.decrypt_patch = patch.object(service, 'decrypt', side_effect=lambda account: self.encrypted[account.credentials])
        self.decrypt_patch.start()

    def tearDown(self):
        self.decrypt_patch.stop()
        self.cipher_patch.stop()
        self.env.stop()
        test_dashboard_database.DashboardDatabaseTests.tearDown(self)

    def data(self, token='user-token'):
        return {'access_token': token, 'refresh_token': 'refresh-secret',
                'workspace_id': WORKSPACE, 'workspace_name': 'Notes'}

    def authorize(self, user_id=None):
        url = service.authorize(self.db, user_id or self.project.owner_id)['authorization_url']
        return parse_qs(urlsplit(url).query)['state'][0]

    def test_state_is_user_bound_single_use_and_not_a_login_token(self):
        state = self.authorize()
        with self.assertRaises(InvalidCredentialsError):
            authenticated_session(self.db, state)
        with patch.object(service, 'token_request', return_value=self.data()) as token:
            with self.assertRaises(HTTPException) as error:
                service.exchange(self.db, 999, 'code', state)
            self.assertEqual(error.exception.status_code, 400)
            token.assert_not_called()
            result = service.exchange(self.db, self.project.owner_id, 'code', state)
            self.assertTrue(result['connected'])
            self.assertNotIn('user-token', str(result))
            with self.assertRaises(HTTPException):
                service.exchange(self.db, self.project.owner_id, 'code', state)
            self.assertEqual(token.call_count, 1)
        self.assertIsNone(self.db.scalar(select(AuthSession).where(AuthSession.token_hash == service.state_hash(state))))
        stored = self.db.get(NotionAccount, self.project.owner_id)
        self.assertNotIn('user-token', stored.credentials)
        self.assertNotIn('refresh-secret', stored.credentials)

    def test_expired_state_does_not_exchange(self):
        state = self.authorize()
        pending = self.db.scalar(select(AuthSession).where(AuthSession.token_hash == service.state_hash(state)))
        pending.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        with patch.object(service, 'token_request') as token, self.assertRaises(HTTPException):
            service.exchange(self.db, self.project.owner_id, 'code', state)
        token.assert_not_called()

    def test_redirect_must_match_frontend_callback_and_allowed_origin(self):
        canonical = 'https://moeum-log.vercel.app/auth/notion/callback'
        with patch.dict(os.environ, {'FRONTEND_ORIGINS': 'https://moeum-log.vercel.app,http://localhost:5173',
                                    'NOTION_OAUTH_REDIRECT_URI': canonical, 'RENDER': 'true'}):
            self.assertEqual(service.config()[2], canonical)
            for invalid in ('http://localhost:5173/auth/notion/callback',
                            'https://other.example/auth/notion/callback',
                            'https://moeum-log.vercel.app/', canonical + '?next=other', canonical + '#fragment'):
                with self.subTest(redirect=invalid), patch.dict(os.environ, {'NOTION_OAUTH_REDIRECT_URI': invalid}):
                    with self.assertRaises(HTTPException) as error:
                        service.config()
                    self.assertEqual(error.exception.status_code, 503)

    def test_local_callback_remains_available_for_local_development(self):
        with patch.dict(os.environ, {'FRONTEND_ORIGINS': 'http://localhost:5173', 'RENDER': ''}):
            self.assertEqual(service.config()[2], 'http://localhost:5173/auth/notion/callback')

    def test_failed_exchange_preserves_previous_connection(self):
        service.store(self.db, self.project.owner_id, self.data('old-token'))
        state = self.authorize()
        with patch.object(service, 'token_request', side_effect=HTTPException(502, 'Unavailable')):
            with self.assertRaises(HTTPException):
                service.exchange(self.db, self.project.owner_id, 'code', state)
        self.db.rollback()
        self.assertEqual(service.user_token(self.db, self.project.owner_id), 'old-token')
        with patch.object(service, 'token_request') as token, self.assertRaises(HTTPException):
            service.exchange(self.db, self.project.owner_id, 'code', state)
        token.assert_not_called()

    def test_two_users_collect_with_their_own_token_and_record_edits(self):
        second = User(user_id='two', name='Two', email='two@example.com', password_hash='unused')
        self.db.add(second)
        self.db.flush()
        project = Project(owner_id=second.id, project_name='Two', notion_url='https://notion.so/' + PAGE)
        self.project.notion_url = project.notion_url
        self.db.add(project)
        self.db.commit()
        service.store(self.db, self.project.owner_id, self.data('first-token'))
        service.store(self.db, second.id, self.data('second-token'))
        for target, expected_token in ((self.project, 'first-token'), (project, 'second-token')):
            self.assertTrue(integrations(target, self.db)['notion']['configured'])
            state = next(c for c in connections(target, self.db)['connections'] if c['source'] == 'notion')
            self.assertEqual(state['connection_status'], 'configured')
            for title, created in (('Before', 0), ('After', 1)):
                page = {**NOTION, 'properties': {'Name': {'type': 'title', 'title': [{'plain_text': title}]}}}
                with patch.object(external_sync, 'fetch_json', side_effect=[page, {'object': 'list', 'results': [], 'has_more': False}, page]) as fetch:
                    result = external_sync.sync_external(self.db, target, 'notion')
                    self.assertEqual(result['created'], created)
                    for call in fetch.call_args_list:
                        self.assertEqual(call.args[2]['Authorization'], 'Bearer ' + expected_token)
            activity = self.db.scalar(select(ProjectActivity).where(ProjectActivity.project_id == target.id))
            self.assertIn('Before', activity.description)
            self.assertIn('After', activity.description)

    def test_unconnected_user_is_not_given_server_token(self):
        with patch.object(external_sync, 'fetch_json') as fetch, self.assertRaises(HTTPException) as error:
            external_sync.scoped_token('notion', self.project.owner_id, PAGE, self.db)
        self.assertEqual(error.exception.status_code, 409)
        fetch.assert_not_called()

    def test_failed_personal_token_never_falls_back_to_server_token(self):
        self.project.notion_url = 'https://notion.so/' + PAGE
        service.store(self.db, self.project.owner_id, self.data())
        with patch.object(external_sync, 'fetch_json', side_effect=HTTPException(404, 'No access')) as fetch:
            with self.assertRaises(HTTPException):
                external_sync.sync_external(self.db, self.project, 'notion')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[2]['Authorization'], 'Bearer user-token')

    def test_initial_collection_checks_personal_connection(self):
        from app.services.initial_sync import initial_sync
        self.project.notion_url = 'https://notion.so/' + PAGE
        service.store(self.db, self.project.owner_id, self.data())
        with patch('app.services.initial_sync.SessionLocal') as factory, patch('app.services.initial_sync.sync_external') as sync:
            factory.return_value.__enter__.return_value = self.db
            initial_sync(self.project.id, self.project.owner_id, ('notion',))
            sync.assert_called_once_with(self.db, self.project, 'notion')

    def test_refresh_is_user_scoped_and_rotates_both_tokens(self):
        service.store(self.db, self.project.owner_id, self.data('old-token'))
        with patch.object(service, 'token_request', return_value={**self.data('new-token'), 'refresh_token': 'new-refresh'}) as token:
            result = service.refresh(self.db, self.project.owner_id)
        self.assertTrue(result['connected'])
        token.assert_called_once_with({'grant_type': 'refresh_token', 'refresh_token': 'refresh-secret'})
        self.assertEqual(service.user_token(self.db, self.project.owner_id), 'new-token')
        self.assertIsNone(service.user_token(self.db, 999))

    def test_oauth_transport_sanitizes_errors_and_uses_basic_auth(self):
        with patch('httpx.Client.post', return_value=httpx.Response(200, json=self.data())) as post:
            self.assertEqual(service.token_request({'code': 'code'})['access_token'], 'user-token')
        self.assertEqual(post.call_args.kwargs['auth'], ('client', 'client-secret'))
        for response in (httpx.Response(401, text='client-secret'), httpx.Response(200, json={}), httpx.Response(200, text='invalid')):
            with patch('httpx.Client.post', return_value=response), self.assertRaises(HTTPException) as error:
                service.token_request({})
            self.assertNotIn('client-secret', str(error.exception.detail))

    def test_migration_creates_only_its_table(self):
        with self.engine.connect() as connection:
            NotionAccount.__table__.drop(connection)
            setup(connection, apply=False)
            setup(connection, apply=True)
            setup(connection, apply=True)
        self.assertIsNotNone(self.db.get(User, self.project.owner_id))


def test_real_encryption_binds_credentials_to_user():
    fernet = pytest.importorskip('cryptography.fernet', reason='cryptography package installation unavailable')
    account = NotionAccount(user_id=1, credentials='unused')
    with patch.dict(os.environ, {'NOTION_CREDENTIAL_ENCRYPTION_KEY': fernet.Fernet.generate_key().decode()}):
        account.credentials = service.cipher().encrypt(json.dumps({'user_id': 1, 'access_token': 'private'}).encode()).decode()
        assert 'private' not in account.credentials
        assert service.decrypt(account)['access_token'] == 'private'
        account.user_id = 2
        with pytest.raises(HTTPException):
            service.decrypt(account)
