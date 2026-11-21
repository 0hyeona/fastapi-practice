import os
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.main import app
from app.models.auth_session import AuthSession
from app.models.figma_account import FigmaAccount
from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.user import User
from app.routers.auth import current_user
from app.routers import figma_oauth as routes
from app.routers.project_connections import connections
from app.routers.project_integrations import integrations
from app.services import external_sync, figma_oauth as service
from app.services.auth_service import InvalidCredentialsError, authenticated_session, utc_now
from scripts.setup_figma_accounts_db import setup as setup_figma_accounts
import test_dashboard_database
from test_external_sync import CURRENT, FIGMA


class FigmaOAuthTests(unittest.TestCase):
    def setUp(self):
        test_dashboard_database.DashboardDatabaseTests.setUp(self)
        self.env = patch.dict(os.environ, {
            'FIGMA_CLIENT_ID': 'client', 'FIGMA_CLIENT_SECRET': 'client-secret',
            'FIGMA_REDIRECT_URI': 'http://localhost:5173/auth/figma/callback',
            'FIGMA_CREDENTIAL_ENCRYPTION_KEY': Fernet.generate_key().decode(),
            # These settings must never affect the OAuth path or grant access.
            'FIGMA_TOKEN': 'server-secret', 'FIGMA_TOKEN_OWNER_ID': '999',
            'FIGMA_ALLOWED_FILE_KEYS': 'OTHER', 'FIGMA_SYNC_MIN_INTERVAL_SECONDS': '0',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        test_dashboard_database.DashboardDatabaseTests.tearDown(self)

    def data(self, token='user-token', identity='12345678901234567890'):
        return {'access_token': token, 'refresh_token': 'refresh-secret',
                'user_id_string': identity, 'expires_in': 3600, 'token_type': 'bearer'}

    def authorize(self):
        url = service.authorize(self.db, self.project.owner_id)['authorization_url']
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(urlsplit(url).netloc, 'www.figma.com')
        self.assertEqual(set(query['scope'][0].split()), set(service.SCOPES))
        self.assertNotIn('client-secret', url)
        return query['state'][0]

    def expire(self, seconds=-1):
        account = self.db.get(FigmaAccount, self.project.owner_id)
        account.expires_at = utc_now() + timedelta(seconds=seconds)
        self.db.commit()

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
            self.assertEqual(result['figma_user_id'], '12345678901234567890')
            self.assertNotIn('user-token', str(result))
            token.assert_called_once_with({'grant_type': 'authorization_code', 'code': 'code',
                                          'redirect_uri': os.environ['FIGMA_REDIRECT_URI']})
            with self.assertRaises(HTTPException):
                service.exchange(self.db, self.project.owner_id, 'code', state)
            self.assertEqual(token.call_count, 1)
        self.assertIsNone(self.db.scalar(select(AuthSession).where(
            AuthSession.token_hash == service.state_hash(state))))

    def test_expired_state_never_contacts_figma(self):
        state = self.authorize()
        pending = self.db.scalar(select(AuthSession).where(AuthSession.token_hash == service.state_hash(state)))
        pending.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        with patch.object(service, 'token_request') as token, self.assertRaises(HTTPException) as error:
            service.exchange(self.db, self.project.owner_id, 'code', state)
        self.assertEqual(error.exception.status_code, 400)
        token.assert_not_called()

    def test_failed_exchange_preserves_old_connection_and_consumes_state(self):
        service.store(self.db, self.project.owner_id, self.data('old-token'))
        state = self.authorize()
        with patch.object(service, 'token_request', side_effect=HTTPException(502, 'Unavailable')):
            with self.assertRaises(HTTPException):
                service.exchange(self.db, self.project.owner_id, 'code', state)
        self.assertEqual(service.user_token(self.db, self.project.owner_id), 'old-token')
        with patch.object(service, 'token_request') as token, self.assertRaises(HTTPException):
            service.exchange(self.db, self.project.owner_id, 'code', state)
        token.assert_not_called()

    def test_real_encryption_binds_credentials_to_user_and_figma_account(self):
        service.store(self.db, self.project.owner_id, self.data())
        account = self.db.get(FigmaAccount, self.project.owner_id)
        self.assertNotIn('user-token', account.credentials)
        self.assertNotIn('refresh-secret', account.credentials)
        self.assertEqual(service.decrypt(account)['access_token'], 'user-token')
        for user_id, identity in ((999, account.figma_user_id), (account.user_id, 'another-account')):
            substituted = FigmaAccount(user_id=user_id, figma_user_id=identity, credentials=account.credentials)
            with self.assertRaises(HTTPException):
                service.decrypt(substituted)
        with patch.dict(os.environ, {'FIGMA_CREDENTIAL_ENCRYPTION_KEY': Fernet.generate_key().decode()}):
            with self.assertRaises(HTTPException) as error:
                service.user_token(self.db, self.project.owner_id)
            self.assertEqual(error.exception.status_code, 503)

    def test_missing_connection_never_falls_back_to_server_token(self):
        self.project.figma_url = 'https://www.figma.com/design/OTHER/Test'
        self.db.commit()
        with patch.dict(os.environ, {'FIGMA_TOKEN_OWNER_ID': str(self.project.owner_id)}):
            with patch.object(external_sync, 'fetch_json') as fetch, self.assertRaises(HTTPException) as error:
                external_sync.sync_external(self.db, self.project, 'figma')
            self.assertEqual(error.exception.status_code, 409)
            fetch.assert_not_called()
        with self.assertRaises(HTTPException) as error:
            external_sync.scoped_token('figma', self.project.owner_id, 'OTHER')
        self.assertEqual(error.exception.status_code, 503)
        self.assertFalse(service.status(self.db, self.project.owner_id)['connected'])

    def test_two_users_and_different_project_files_use_owner_tokens(self):
        second = User(user_id='two', name='Two', email='two@example.com', password_hash='unused')
        self.db.add(second)
        self.db.flush()
        project = Project(owner_id=second.id, project_name='Two', figma_url='https://figma.com/design/SECOND/Test')
        self.project.figma_url = 'https://figma.com/design/FIRST/Test'
        self.other.figma_url = 'https://figma.com/design/THIRD/Test'
        self.db.add(project)
        self.db.commit()
        service.store(self.db, self.project.owner_id, self.data('first-token'))
        service.store(self.db, second.id, self.data('second-token', '22222222222222222222'))
        for target, expected in ((self.project, 'first-token'), (self.other, 'first-token'), (project, 'second-token')):
            self.assertTrue(integrations(target, self.db)['figma']['configured'])
            connection = next(c for c in connections(target, self.db)['connections'] if c['source'] == 'figma')
            self.assertEqual(connection['connection_status'], 'configured')
            for created in (1, 0):
                with patch.object(external_sync, 'fetch_json', side_effect=[FIGMA, CURRENT]) as fetch:
                    result = external_sync.sync_external(self.db, target, 'figma')
                self.assertEqual(result['created'], created)
                for call in fetch.call_args_list:
                    self.assertEqual(call.args[2], {'Authorization': 'Bearer ' + expected})
        self.assertEqual(len(self.db.scalars(select(ProjectActivity)).all()), 3)

    def test_fresh_token_does_not_refresh_or_require_client_config(self):
        service.store(self.db, self.project.owner_id, self.data())
        with patch.dict(os.environ, {'FIGMA_CLIENT_SECRET': ''}):
            with patch.object(service, 'token_request') as token:
                self.assertEqual(service.user_token(self.db, self.project.owner_id), 'user-token')
                self.assertIsNone(service.user_token(self.db, 999))
            token.assert_not_called()

    def test_expiring_token_refreshes_and_preserves_reusable_refresh_token(self):
        service.store(self.db, self.project.owner_id, self.data('old-token'))
        self.expire(seconds=30)
        with patch.object(service, 'token_request', return_value={'access_token': 'new-token', 'expires_in': 3600}) as token:
            self.assertEqual(service.user_token(self.db, self.project.owner_id), 'new-token')
            self.assertEqual(service.user_token(self.db, self.project.owner_id), 'new-token')
        token.assert_called_once_with({'refresh_token': 'refresh-secret'}, refresh=True)
        self.db.rollback()
        self.db.expire_all()
        account = self.db.get(FigmaAccount, self.project.owner_id)
        self.assertEqual(service.decrypt(account)['refresh_token'], 'refresh-secret')
        self.assertGreater(account.expires_at, utc_now() + timedelta(minutes=50))

    def test_manual_refresh_rotates_refresh_token_if_figma_returns_one(self):
        service.store(self.db, self.project.owner_id, self.data())
        with patch.object(service, 'token_request', return_value={**self.data('new-token'), 'refresh_token': 'new-refresh'}):
            self.assertTrue(service.refresh(self.db, self.project.owner_id)['connected'])
        self.assertEqual(service.decrypt(self.db.get(FigmaAccount, self.project.owner_id))['refresh_token'], 'new-refresh')
        with self.assertRaises(HTTPException) as error:
            service.refresh(self.db, self.other.owner_id + 100)
        self.assertEqual(error.exception.status_code, 409)

    def test_refresh_rechecks_account_updated_by_another_session(self):
        service.store(self.db, self.project.owner_id, self.data('old-token'))
        self.expire()
        stale = self.db.get(FigmaAccount, self.project.owner_id)
        with Session(self.engine) as other:
            service.store(other, self.project.owner_id, self.data('already-refreshed'))
        self.assertEqual(service.decrypt(stale)['access_token'], 'old-token')
        with patch.object(service, 'token_request') as token:
            self.assertEqual(service.user_token(self.db, self.project.owner_id), 'already-refreshed')
        token.assert_not_called()

    def test_failed_refresh_preserves_account_and_blocks_file_collection(self):
        service.store(self.db, self.project.owner_id, self.data('old-token'))
        self.project.figma_url = 'https://figma.com/design/ABC123/Test'
        self.expire()
        with patch.object(service, 'token_request', side_effect=HTTPException(409, 'Reconnect')):
            with patch.object(external_sync, 'fetch_json') as fetch, self.assertRaises(HTTPException) as error:
                external_sync.sync_external(self.db, self.project, 'figma')
            self.assertEqual(error.exception.status_code, 409)
            fetch.assert_not_called()
        account = self.db.get(FigmaAccount, self.project.owner_id)
        self.assertEqual(service.decrypt(account)['access_token'], 'old-token')

    def test_oauth_transport_uses_basic_auth_and_separate_form_endpoints(self):
        for refresh, endpoint, payload in ((False, 'token', {'code': 'code'}),
                                           (True, 'refresh', {'refresh_token': 'refresh-secret'})):
            with patch('httpx.Client.post', return_value=httpx.Response(200, json=self.data())) as post:
                service.token_request(payload, refresh=refresh)
            self.assertEqual(post.call_args.args[0], 'https://api.figma.com/v1/oauth/' + endpoint)
            self.assertEqual(post.call_args.kwargs['auth'], ('client', 'client-secret'))
            self.assertEqual(post.call_args.kwargs['data'], payload)
            self.assertNotIn('json', post.call_args.kwargs)

    def test_invalid_responses_and_errors_do_not_leak_secrets(self):
        responses = [httpx.Response(401, text='client-secret'), httpx.Response(200, text='not-json')]
        for data in ({}, [], {**self.data(), 'expires_in': True}, {**self.data(), 'expires_in': -1},
                     {**self.data(), 'access_token': ''}, {**self.data(), 'expires_in': 1.5}):
            responses.append(httpx.Response(200, json=data))
        for response in responses:
            with patch('httpx.Client.post', return_value=response), self.assertRaises(HTTPException) as error:
                service.token_request({})
            self.assertEqual(error.exception.status_code, 502)
            self.assertNotIn('client-secret', str(error.exception.detail))
        with patch('httpx.Client.post', return_value=httpx.Response(400, text='refresh-secret')):
            with self.assertRaises(HTTPException) as error:
                service.token_request({}, refresh=True)
            self.assertEqual(error.exception.status_code, 409)
            self.assertNotIn('refresh-secret', str(error.exception.detail))
        with patch('httpx.Client.post', return_value=httpx.Response(429, headers={'Retry-After': '30'})):
            with self.assertRaises(HTTPException) as error:
                service.token_request({})
            self.assertEqual(error.exception.headers, {'Retry-After': '30'})
        for exception, expected in ((httpx.ReadTimeout('client-secret'), 504), (httpx.ConnectError('client-secret'), 502)):
            with patch('httpx.Client.post', side_effect=exception), self.assertRaises(HTTPException) as error:
                service.token_request({})
            self.assertEqual(error.exception.status_code, expected)
            self.assertNotIn('client-secret', str(error.exception.detail))

    def test_missing_config_fails_before_saving_state(self):
        for setting in ({'FIGMA_CLIENT_ID': ''}, {'FIGMA_CLIENT_SECRET': ''},
                        {'FIGMA_REDIRECT_URI': 'http://example.com/callback'},
                        {'FIGMA_REDIRECT_URI': 'https://user:password@example.com/callback'},
                        {'FIGMA_CREDENTIAL_ENCRYPTION_KEY': 'invalid'}):
            with patch.dict(os.environ, setting), self.assertRaises(HTTPException) as error:
                service.authorize(self.db, self.project.owner_id)
            self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(len(self.db.scalars(select(AuthSession)).all()), 0)

    def test_routes_use_login_dependency_and_reject_request_user_id(self):
        paths = app.openapi()['paths']
        for path, method in (('/api/integrations/figma', 'get'),
                             ('/api/integrations/figma/authorize', 'post'),
                             ('/api/integrations/figma/exchange', 'post'),
                             ('/api/integrations/figma/refresh', 'post')):
            self.assertTrue(paths[path][method]['security'])
        for route in routes.router.routes:
            self.assertIn(current_user, [dependency.call for dependency in route.dependant.dependencies])
        result = {'connected': True, 'figma_user_id': '123', 'expires_at': utc_now()}
        body = {'code': 'code', 'state': 's' * 43}
        with self.assertRaises(ValidationError):
            routes.ExchangeRequest(**body, user_id=999)
        with patch.object(service, 'exchange', return_value=result) as exchange:
            request = routes.ExchangeRequest(**body)
            response = routes.FigmaStatus.model_validate(routes.exchange(
                request, user=SimpleNamespace(id=42), db=self.db)).model_dump()
        exchange.assert_called_once_with(self.db, 42, 'code', 's' * 43)
        self.assertNotIn('credentials', response)
        self.assertNotIn('access_token', response)

    def test_setup_preserves_existing_table_and_creates_only_its_table(self):
        with self.engine.connect() as connection:
            before = set(inspect(connection).get_table_names())
            FigmaAccount.__table__.drop(connection)
            connection.commit()
            setup_figma_accounts(connection, apply=False)
            self.assertFalse(inspect(connection).has_table('figma_accounts'))
            setup_figma_accounts(connection, apply=True)
            setup_figma_accounts(connection, apply=True)
            self.assertEqual(set(inspect(connection).get_table_names()), before)
        self.assertIsNotNone(self.db.get(User, self.project.owner_id))

    def test_setup_rejects_incompatible_existing_table_without_altering_it(self):
        with self.engine.connect() as connection:
            FigmaAccount.__table__.drop(connection)
            connection.execute(text('CREATE TABLE figma_accounts (user_id INTEGER PRIMARY KEY, old_token TEXT)'))
            connection.commit()
            with self.assertRaises(RuntimeError):
                setup_figma_accounts(connection, apply=True)
            self.assertEqual({column['name'] for column in inspect(connection).get_columns('figma_accounts')},
                             {'user_id', 'old_token'})
