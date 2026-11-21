import copy
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database.database import Base
from app.figma_plugin_cors import FigmaPluginCORSMiddleware
from app.models.figma_plugin import FigmaPluginConnection, ProjectFigmaSnapshot
from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.project_sync_run import ProjectSyncRun
from app.models.story import Story
from app.models.user import User
from app.routers import project_integrations
from app.services import figma_plugin as service
from app.services.auth_service import InvalidCredentialsError, authenticated_session, utc_now
from app.services.figma_sync_policy import rate_limit_message, state

URL = 'https://www.figma.com/design/FILE123/Test'


def document(text='Before'):
    return {'id': '0:0', 'name': 'Document', 'type': 'DOCUMENT', 'children': [
        {'id': '0:1', 'name': 'Page', 'type': 'CANVAS', 'children': [
            {'id': '1:1', 'name': 'Label', 'type': 'TEXT', 'characters': text,
             'absoluteBoundingBox': {'x': 20, 'y': 30, 'width': 100, 'height': 20}}
        ]}
    ]}


class FigmaPluginTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        with self.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(user_id='owner', name='Owner', email='owner@example.com', password_hash='unused')
        self.other_user = User(user_id='other', name='Other', email='other@example.com', password_hash='unused')
        self.db.add_all([self.user, self.other_user])
        self.db.flush()
        self.project = Project(owner_id=self.user.id, project_name='Demo', figma_url=URL)
        self.db.add(self.project)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def paired(self):
        code = service.create_pairing(self.db, self.project, self.user.id)['code']
        return service.pair(self.db, code, URL)['token']

    def push(self, token, sequence, text='Before', **changes):
        data = dict(sequence=sequence, file_url=URL, name='Demo', document=document(text))
        data.update(changes)
        return service.receive(self.db, token, **data)

    def activities(self):
        return self.db.scalars(select(ProjectActivity).order_by(ProjectActivity.id)).all()

    def test_only_owner_can_issue_or_revoke_codes(self):
        for action in (service.create_pairing, service.disconnect):
            with self.assertRaises(HTTPException) as error:
                action(self.db, self.project, self.other_user.id)
            self.assertEqual(error.exception.status_code, 403)

    def test_pairing_is_single_use_expiring_and_never_a_login(self):
        code = service.create_pairing(self.db, self.project, self.user.id)['code']
        row = self.db.get(FigmaPluginConnection, self.project.id)
        self.assertNotEqual(row.pairing_hash, code)
        token = service.pair(self.db, code, URL)['token']
        for secret in (code, token):
            with self.assertRaises(InvalidCredentialsError):
                authenticated_session(self.db, secret)
        with self.assertRaises(HTTPException):
            service.pair(self.db, code, URL)
        code = service.create_pairing(self.db, self.project, self.user.id)['code']
        row.pairing_expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException):
            service.pair(self.db, code, URL)

    def test_wrong_file_does_not_consume_pairing_code(self):
        code = service.create_pairing(self.db, self.project, self.user.id)['code']
        with self.assertRaises(HTTPException) as error:
            service.pair(self.db, code, 'https://www.figma.com/design/OTHER/Test')
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn('token', service.pair(self.db, code, URL))

    def test_baseline_then_edit_updates_once_and_survives_reload(self):
        token = self.paired()
        with patch('app.services.external_sync.fetch_json', side_effect=AssertionError('no REST')):
            self.assertTrue(self.push(token, 1)['baseline'])
            self.assertEqual(self.activities(), [])
            self.assertEqual(self.push(token, 2, 'After')['created'], 1)
            self.db.expire_all()
            self.assertEqual(self.push(token, 3, 'After')['created'], 0)
        saved = self.activities()
        self.assertEqual(len(saved), 1)
        self.assertIn('Before → After', saved[0].description)
        self.assertEqual(saved[0].source, 'figma')
        self.assertEqual(saved[0].activity_type, 'design_updated')

    def test_retries_and_out_of_order_uploads_never_overwrite_latest_snapshot(self):
        token = self.paired()
        self.push(token, 1)
        self.push(token, 3, 'Newest')
        self.assertTrue(self.push(token, 2, 'Older')['duplicate'])
        self.assertTrue(self.push(token, 3, 'Newest')['duplicate'])
        snapshot = self.db.get(ProjectFigmaSnapshot, self.project.id)
        self.assertEqual(snapshot.content['nodes']['1:1']['props']['characters'], 'Newest')
        self.assertEqual(len(self.activities()), 1)

    def test_reverting_to_previous_content_is_a_new_change_and_preserves_story(self):
        token = self.paired()
        self.push(token, 1)
        self.push(token, 2, 'After')
        story = Story(project_id=self.project.id, title='Story', content='')
        self.db.add(story)
        self.db.flush()
        self.activities()[0].story_id = story.id
        self.db.commit()
        self.push(token, 3, 'Before')
        saved = self.activities()
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0].story_id, story.id)
        self.assertNotEqual(saved[0].external_id, saved[1].external_id)

    def test_additions_deletions_and_style_edits_are_in_description(self):
        token = self.paired()
        self.push(token, 1)
        doc = document()
        doc['children'][0]['children'] = [{'id': '1:2', 'name': 'Box', 'type': 'RECTANGLE', 'opacity': .5}]
        self.push(token, 2, document=doc)
        self.assertIn('추가 1개 · 삭제 1개', self.activities()[0].description)
        doc['children'][0]['children'][0]['opacity'] = 1
        self.push(token, 3, document=doc)
        self.assertIn('불투명도: 0.5 → 1', self.activities()[1].description)

    def test_active_rest_429_remains_but_does_not_block_editor_updates(self):
        self.db.add(ProjectSyncRun(project_id=self.project.id, source='figma', status='failed',
            started_at=utc_now(), finished_at=utc_now(), error_code=429,
            error_message=rate_limit_message(HTTPException(429, headers={'Retry-After': '400000'}))))
        self.db.commit()
        token = self.paired()
        self.push(token, 1)
        self.assertEqual(self.push(token, 2, 'After')['created'], 1)
        self.assertFalse(state(self.db, self.project.id)['can_sync'])
        status = project_integrations.figma_sync_status(self.project, self.db)
        self.assertEqual(status['transport'], 'plugin')
        with patch('app.services.external_sync.fetch_json', side_effect=AssertionError('no REST')):
            result = project_integrations.sync_figma(self.project, self.db, None)
        self.assertEqual(result['created'], 0)

    def test_new_pairing_replaces_previous_plugin_and_disconnect_revokes_it(self):
        token = self.paired()
        replacement = self.paired()
        with self.assertRaises(HTTPException):
            self.push(token, 1)
        self.push(replacement, 1)
        service.disconnect(self.db, self.project, self.user.id)
        with self.assertRaises(HTTPException):
            self.push(replacement, 2)
        self.assertFalse(service.status(self.db, self.project)['enabled'])

    def test_expired_session_changed_owner_changed_file_and_disabled_user_are_rejected(self):
        for change in ('expiry', 'owner', 'file', 'user'):
            with self.subTest(change=change):
                self.project.owner_id = self.user.id
                self.project.figma_url = URL
                self.user.account_status = 'active'
                self.db.commit()
                token = self.paired()
                if change == 'expiry':
                    self.db.get(FigmaPluginConnection, self.project.id).expires_at = utc_now() - timedelta(seconds=1)
                elif change == 'owner': self.project.owner_id = self.other_user.id
                elif change == 'file': self.project.figma_url = 'https://www.figma.com/design/OTHER/Test'
                else: self.user.account_status = 'disabled'
                self.db.commit()
                with self.assertRaises(HTTPException) as error:
                    self.push(token, 1)
                self.assertEqual(error.exception.status_code, 401)

    def test_wrong_file_malformed_snapshot_and_failed_commit_preserve_baseline(self):
        token = self.paired()
        self.push(token, 1)
        bad = document()
        bad['children'][0]['children'].append(copy.deepcopy(bad['children'][0]['children'][0]))
        for changes in ({'file_url': 'https://www.figma.com/design/OTHER/Test'}, {'document': bad},
                        {'document': {'type': 'CANVAS'}}):
            with self.assertRaises(HTTPException): self.push(token, 2, 'After', **changes)
        with patch.object(self.db, 'commit', side_effect=RuntimeError('simulated failure')):
            with self.assertRaises(RuntimeError): self.push(token, 2, 'After')
        self.assertEqual(self.activities(), [])
        self.assertEqual(self.db.get(ProjectFigmaSnapshot, self.project.id).content['nodes']['1:1']['props']['characters'], 'Before')
        self.assertEqual(self.push(token, 2, 'After')['created'], 1)


def immediate(coroutine):
    """Run in-memory ASGI helpers that do not schedule I/O or use a socketpair."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError('Unexpected asynchronous I/O')


class FigmaPluginTransportTests(unittest.TestCase):
    def test_setup_creates_only_plugin_tables_and_can_be_repeated(self):
        from sqlalchemy import inspect
        from scripts.setup_figma_plugin_db import setup
        engine = create_engine('sqlite://')
        User.__table__.create(engine)
        Project.__table__.create(engine)
        with engine.connect() as connection:
            setup(connection, apply=False)
            self.assertEqual(set(inspect(connection).get_table_names()), {'users', 'projects'})
            setup(connection, apply=True)
            setup(connection, apply=True)
            self.assertEqual(set(inspect(connection).get_table_names()), {
                'users', 'projects', 'figma_plugin_connections', 'project_figma_snapshots'})
        engine.dispose()

    def test_plugin_cors_is_scoped_to_two_endpoints(self):
        async def request(path):
            messages = []
            async def app(scope, receive, send):
                await send({'type': 'http.response.start', 'status': 418, 'headers': []})
                await send({'type': 'http.response.body', 'body': b''})
            async def receive(): return {'type': 'http.request', 'body': b''}
            async def send(message): messages.append(message)
            middleware = FigmaPluginCORSMiddleware(app)
            await middleware({'type': 'http', 'method': 'OPTIONS', 'path': path,
                'headers': [(b'origin', b'null'), (b'access-control-request-method', b'POST'),
                            (b'access-control-request-headers', b'authorization,content-type')]}, receive, send)
            return messages[0]
        allowed = immediate(request('/api/figma-plugin/snapshot'))
        self.assertEqual(allowed['status'], 200)
        self.assertIn((b'access-control-allow-origin', b'null'), allowed['headers'])
        self.assertEqual(immediate(request('/api/auth/login'))['status'], 418)

    def test_invalid_json_and_oversized_body_do_not_echo_secrets(self):
        from app.routers.figma_plugin import bounded_json, PairRequest
        class Request:
            async def stream(self): yield b'{"code":"secret"}'
        for limit, code in ((100, 422), (2, 413)):
            with self.assertRaises(HTTPException) as error:
                immediate(bounded_json(Request(), PairRequest, limit))
            self.assertEqual(error.exception.status_code, code)
            self.assertNotIn('secret', str(error.exception.detail))
