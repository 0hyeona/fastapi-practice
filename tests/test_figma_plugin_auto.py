import copy
import unittest
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import inspect, create_engine, text
from app.models.figma_plugin import FigmaPluginConnection, ProjectFigmaSnapshot
from app.models.project_sync_run import ProjectSyncRun
from app.models.project_activity import ProjectActivity
from app.models.story import Story
from sqlalchemy import select
from app.services import figma_plugin as service
from app.services.auth_service import utc_now
from tests import test_figma_plugin as existing
URL, document = existing.URL, existing.document

class AutomaticCollectionTests(unittest.TestCase):
    setUp = existing.FigmaPluginTests.setUp
    tearDown = existing.FigmaPluginTests.tearDown
    paired = existing.FigmaPluginTests.paired
    push = existing.FigmaPluginTests.push
    activities = existing.FigmaPluginTests.activities
    def delta(self, token, sequence, upserts, deleted=None, revision=None):
        saved = self.db.get(ProjectFigmaSnapshot, self.project.id)
        return service.receive(self.db, token, sequence, URL, 'Demo', None,
            delta={'upserts': upserts, 'deleted': deleted or []},
            base_revision=saved.revision if revision is None else revision)

    def test_resume_reuses_secret_preserves_absolute_expiry_and_reports_server_sequence(self):
        token = self.paired()
        self.push(token, 1)
        row = self.db.get(FigmaPluginConnection, self.project.id)
        row.expires_at = utc_now() + timedelta(hours=1)
        self.db.commit()
        expires_at = row.expires_at
        result = service.resume(self.db, token, URL, 'sending')
        self.assertEqual(result['last_sequence'], 1)
        self.assertEqual(row.expires_at, expires_at)
        self.push(token, 2, 'Updated')
        self.assertEqual(row.expires_at, expires_at)
        service.resume(self.db, token, URL, 'sending')
        self.assertEqual(service.status(self.db, self.project)['collection_state'], 'sending')
        row.last_seen_at = utc_now() - timedelta(seconds=76)
        self.db.commit()
        self.assertEqual(service.status(self.db, self.project)['collection_state'], 'offline')
        service.disconnect(self.db, self.project, self.user.id)
        with self.assertRaises(HTTPException): service.resume(self.db, token, URL)

    def test_text_color_size_creation_deletion_and_duplicate_batches(self):
        token = self.paired()
        self.push(token, 1)
        node = dict(document()['children'][0]['children'][0], children=[], parent='0:1')
        node.pop('absoluteBoundingBox')
        node.update(characters='After', fills=[{'type':'SOLID','color':{'r':1,'g':0,'b':0}}], size=[200,40])
        result = self.delta(token, 2, [node])
        self.assertEqual(result['created'], 1)
        duplicate = self.delta(token, 2, [node], revision=0)
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(duplicate['revision'], result['revision'])
        parent = {'id':'0:1','type':'CANVAS','name':'Page','parent':'0:0','children':['1:1','2:1']}
        frame = {'id':'2:1','type':'FRAME','name':'New','parent':'0:1','children':[]}
        self.assertEqual(self.delta(token, 3, [parent,frame])['created'], 1)
        parent['children'] = ['1:1']
        self.assertEqual(self.delta(token, 4, [parent], ['2:1'])['created'], 1)
        self.assertEqual(len(self.activities()), 3)
        self.assertIn('Before → After', self.activities()[0].description)
        self.assertIn('채우기', self.activities()[0].description)
        self.assertIn('크기', self.activities()[0].description)

    def test_stale_revision_and_invalid_tree_preserve_all_records(self):
        token = self.paired()
        self.push(token, 1)
        for upserts, deleted, revision in [([],[],0),([],['0:0'],1),
                ([{'id':'9:9','type':'FRAME','name':'orphan','children':[]}],[],1)]:
            with self.assertRaises(HTTPException) as error:
                self.delta(token, 2, upserts, deleted, revision)
            self.assertEqual(error.exception.status_code,409)
        self.assertEqual(self.activities(),[])
        self.assertEqual(self.db.get(FigmaPluginConnection,self.project.id).last_sequence,1)

    def test_failed_commit_retry_and_restart_final_state_reconciliation(self):
        from unittest.mock import patch
        token = self.paired()
        self.push(token, 1)
        node = dict(document('Edited')['children'][0]['children'][0], children=[])
        with patch.object(self.db,'commit',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError): self.delta(token,2,[node])
        self.assertEqual(self.activities(),[])
        self.assertEqual(self.delta(token,2,[node])['created'],1)
        service.resume(self.db,token,URL)
        self.assertEqual(self.push(token,3,'Final offline state')['created'],1)
        self.assertEqual(self.push(token,4,'Final offline state')['created'],0)

    def test_expired_or_revoked_credentials_never_resume_or_write(self):
        token = self.paired()
        self.push(token, 1)
        row = self.db.get(FigmaPluginConnection, self.project.id)
        row.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        self.assertFalse(service.status(self.db, self.project)['connected'])
        self.assertEqual(service.status(self.db, self.project)['collection_state'], 'offline')
        for action in (lambda: service.resume(self.db, token, URL), lambda: self.push(token, 2, 'Denied')):
            with self.assertRaises(HTTPException) as error:
                action()
            self.assertEqual(error.exception.status_code, 401)
        fresh = self.paired()
        with self.assertRaises(HTTPException):
            service.resume(self.db, token, URL)
        with self.assertRaises(HTTPException):
            service.resume(self.db, fresh, URL.replace('FILE123', 'OTHER'))
        self.user.account_status = 'disabled'
        self.db.commit()
        with self.assertRaises(HTTPException):
            service.resume(self.db, fresh, URL)
        self.assertEqual(self.activities(), [])

    def test_node_properties_flow_into_existing_activities_and_story(self):
        from app.schemas.story import StoryCreate
        from app.services import project_content_service as content
        token = self.paired()
        self.push(token, 1)
        node = dict(document()['children'][0]['children'][0], children=[])
        node.update(name='Renamed', style={'fontSize': 24, 'fontName': {'family': 'Inter', 'style': 'Bold'}},
                    layoutMode='HORIZONTAL', paddingLeft=16, componentProperties={'Label': {'value': 'New'}},
                    position=[40, 50])
        node.pop('absoluteBoundingBox')
        self.delta(token, 2, [node])
        row = self.activities()[0]
        for label in ('이름', '글꼴 스타일', '자동 배치 방향', '컴포넌트 속성', '위치'):
            self.assertIn(label, row.description)
        story = content.create(self.db, Story, StoryCreate(project_id=self.project.id,
                               title='Design update', activity_ids=[row.id]), self.user.id)
        self.db.expire_all()
        self.assertEqual(self.db.get(ProjectActivity, row.id).story_id, story.id)
        self.assertEqual(content.get(self.db, Story, story.id, self.user.id).title, 'Design update')

    def test_failure_history_is_safe_and_success_timestamp_is_preserved(self):
        token = self.paired()
        self.push(token, 1)
        timestamp = service.status(self.db, self.project)['last_received_at']
        with self.assertRaises(HTTPException):
            self.delta(token, 2, [], revision=0)
        run = self.db.scalar(select(ProjectSyncRun).order_by(ProjectSyncRun.id.desc()))
        self.assertEqual(run.error_code, 409)
        self.assertTrue(run.error_message.startswith('Figma plugin:'))
        self.assertNotIn(token, run.error_message)
        self.assertEqual(service.status(self.db, self.project)['collection_state'], 'error')
        self.assertEqual(service.status(self.db, self.project)['last_received_at'], timestamp)
        service.create_pairing(self.db, self.project, self.user.id)
        self.assertEqual(service.status(self.db, self.project)['last_received_at'], timestamp)

    def test_delta_json_gzip_contract_and_status_response(self):
        import gzip
        import json
        from app.routers.figma_plugin import receive_delta, PluginStatus
        token = self.paired()
        self.push(token, 1)
        payload = {'sequence': 2, 'file_url': URL, 'name': 'Demo', 'base_revision': 1,
                   'upserts': [dict(document('Transport')['children'][0]['children'][0], children=[])],
                   'deleted': []}
        raw = json.dumps(payload).encode()
        result = receive_delta(self.db, token, raw, False)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['last_sequence'], 2)
        self.assertTrue(receive_delta(self.db, token, gzip.compress(raw), True)['duplicate'])
        response = PluginStatus.model_validate(service.status(self.db, self.project))
        self.assertTrue(response.connected)
        self.assertEqual(response.collection_state, 'collecting')
        payload['sequence'] = True
        with self.assertRaises(HTTPException) as error:
            receive_delta(self.db, token, json.dumps(payload).encode(), False)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(len(self.activities()), 1)

class MigrationTests(unittest.TestCase):
    def test_existing_tables_upgrade_without_losing_records_and_rerun(self):
        from scripts.setup_figma_plugin_db import setup
        from app.database.database import Base
        engine=create_engine('sqlite://')
        Base.metadata.create_all(engine)
        from sqlalchemy.orm import Session
        from app.models.user import User
        from app.models.project import Project
        with Session(engine) as db:
            user = User(user_id='preserved', name='Owner', email='preserved@example.com', password_hash='unused')
            db.add(user)
            db.flush()
            project = Project(owner_id=user.id, project_name='Preserved', figma_url=URL)
            db.add(project)
            db.flush()
            db.add(FigmaPluginConnection(project_id=project.id, user_id=user.id,
                                         resource_id='FILE123', last_sequence=7))
            db.add(Story(project_id=project.id, title='Preserved story', content='Keep'))
            db.commit()
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE figma_plugin_connections DROP COLUMN last_seen_at'))
            conn.execute(text('ALTER TABLE figma_plugin_connections DROP COLUMN collection_state'))
        with engine.connect() as conn:
            setup(conn,apply=False)
            self.assertNotIn('last_seen_at',{c['name'] for c in inspect(conn).get_columns('figma_plugin_connections')})
            setup(conn,apply=True)
            setup(conn,apply=True)
            self.assertIn('last_seen_at',{c['name'] for c in inspect(conn).get_columns('figma_plugin_connections')})
            self.assertEqual(conn.scalar(text('SELECT last_sequence FROM figma_plugin_connections')), 7)
            self.assertEqual(conn.scalar(text('SELECT title FROM stories')), 'Preserved story')
            self.assertEqual(conn.scalar(text('SELECT COUNT(*) FROM users')), 1)
            conn.execute(text('ALTER TABLE figma_plugin_connections DROP COLUMN collection_state'))
            conn.execute(text('ALTER TABLE figma_plugin_connections ADD COLUMN collection_state INTEGER NULL'))
            conn.commit()
            with self.assertRaisesRegex(RuntimeError, 'expected nullable VARCHAR'):
                setup(conn, apply=True)
            self.assertEqual(conn.scalar(text('SELECT last_sequence FROM figma_plugin_connections')), 7)
        engine.dispose()


class AutomaticTransportTests(unittest.TestCase):
    def test_cors_only_allows_plugin_origins_and_post_on_four_paths(self):
        from app.figma_plugin_cors import FigmaPluginCORSMiddleware
        async def request(path, origin, method='POST'):
            messages = []
            async def app(scope, receive, send):
                await send({'type': 'http.response.start', 'status': 418, 'headers': []})
                await send({'type': 'http.response.body', 'body': b''})
            async def receive():
                return {'type': 'http.request', 'body': b''}
            async def send(message):
                messages.append(message)
            await FigmaPluginCORSMiddleware(app)({'type': 'http', 'method': 'OPTIONS', 'path': path,
                'headers': [(b'origin', origin.encode()), (b'access-control-request-method', method.encode()),
                            (b'access-control-request-headers', b'authorization,content-type')]}, receive, send)
            return messages[0]
        for suffix in ('pair', 'snapshot', 'resume', 'changes'):
            path = '/api/figma-plugin/' + suffix
            for origin in ('null', 'https://www.figma.com'):
                response = existing.immediate(request(path, origin))
                self.assertEqual(response['status'], 200)
                self.assertIn((b'access-control-allow-origin', origin.encode()), response['headers'])
            self.assertEqual(existing.immediate(request(path, 'https://evil.example'))['status'], 400)
            self.assertEqual(existing.immediate(request(path, 'null', 'GET'))['status'], 400)
        self.assertEqual(existing.immediate(request('/api/auth/login', 'null'))['status'], 418)
