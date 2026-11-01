import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import httpx
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, func
from app.main import app
from app.models.project_activity import ProjectActivity
from app.services import external_sync as service
from app.services.initial_sync import initial_sync, queue_initial_sync
from app.schemas.project_activity import ProjectActivityUpdate
from app.schemas.project_github import Dashboard
from app.services import project_content_service as content
from app.routers.project_github import dashboard
from app.routers.project_integrations import integrations
from app.routers import projects as project_routes
from app.schemas.project import ProjectCreate, ProjectUpdate
import test_dashboard_database

PAGE = 'a' * 32
DATE = '2026-11-01T00:00:00Z'
FIGMA = {'versions':[{'id':'10','created_at':DATE,'label':'Design v1','description':'Header'}], 'pagination':{}}
CURRENT = {'version':'10','name':'Design','lastModified':DATE}
NOTION = {'object':'page','id':PAGE,'last_edited_time':DATE,
          'properties':{'Name':{'type':'title','title':[{'plain_text':'Notes'}]}}}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        test_dashboard_database.DashboardDatabaseTests.setUp(self)
        self.project.github_url = None
        self.project.figma_url = 'https://www.figma.com/design/ABC123/Test'
        self.project.notion_url = 'https://www.notion.so/Notes-' + PAGE
        self.db.commit()
        self.env = patch.dict(os.environ, {'FIGMA_TOKEN':'test-figma-token', 'FIGMA_TOKEN_OWNER_ID':str(self.project.owner_id),
            'FIGMA_ALLOWED_FILE_KEYS':'ABC123', 'NOTION_TOKEN':'test-notion-token',
            'NOTION_TOKEN_OWNER_ID':str(self.project.owner_id), 'NOTION_ALLOWED_PAGE_IDS':PAGE})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        test_dashboard_database.DashboardDatabaseTests.tearDown(self)

    def sync_figma(self):
        with patch.object(service, 'fetch_json', side_effect=[FIGMA, CURRENT]):
            return service.sync_external(self.db, self.project, 'figma')

    def sync_notion(self, data=NOTION):
        with patch.object(service, 'fetch_json', return_value=data):
            return service.sync_external(self.db, self.project, 'notion')

    def test_collect_deduplicate_and_preserve_story(self):
        self.assertEqual(self.sync_figma()['created'],1)
        self.assertEqual(self.sync_notion()['created'],1)
        story = test_dashboard_database.DashboardDatabaseTests.story(self)
        activity = self.db.scalar(select(ProjectActivity).where(ProjectActivity.source=='figma'))
        content.update(self.db, ProjectActivity, activity.id, self.project.owner_id, ProjectActivityUpdate(story_id=story.id))
        self.assertEqual(self.sync_figma()['created'],0)
        self.assertEqual(self.sync_notion()['created'],0)
        self.assertEqual(activity.story_id,story.id)
        result = Dashboard.model_validate(dashboard(self.project,self.db))
        self.assertEqual(result.unorganized_counts.figma,0)
        self.assertEqual(result.unorganized_counts.notion,1)
        changed = {**NOTION,'last_edited_time':'2026-11-01T01:00:00Z'}
        self.assertEqual(self.sync_notion(changed)['created'],1)
        self.assertEqual(Dashboard.model_validate(dashboard(self.project,self.db)).unorganized_counts.notion,2)

    def test_url_validation(self):
        self.assertEqual(service.resource_id('notion',f'https://abc.notion.site/Notes-{PAGE}?v=ignored'),PAGE)
        for source,url in [('figma','https://figma.com.evil/design/ABC123/X'),('figma','https://user@figma.com/file/ABC123/X'),
                           ('figma','http://figma.com/file/ABC123/X'),('notion','https://evil.com/'+PAGE),
                           ('notion','https://www.notion.so/without-id'),('figma','https://figma.com/files/team/123')]:
            with self.subTest(url=url), self.assertRaises(HTTPException) as e:
                service.resource_id(source,url)
            self.assertEqual(e.exception.status_code,422)
        with self.assertRaises(HTTPException) as e:
            service.resource_id('notion',None)
        self.assertEqual(e.exception.status_code,409)

    def test_credentials_are_scoped_before_network(self):
        for setting in ({'FIGMA_TOKEN':''},{'FIGMA_TOKEN_OWNER_ID':'999'},{'FIGMA_ALLOWED_FILE_KEYS':'OTHER'}):
            with patch.dict(os.environ,setting), patch.object(service,'fetch_json') as get:
                with self.assertRaises(HTTPException):
                    service.sync_external(self.db,self.project,'figma')
                get.assert_not_called()
                self.assertFalse(integrations(self.project)['figma']['configured'])
        status = str(integrations(self.project))
        self.assertNotIn('test-figma-token',status)
        self.assertNotIn('test-notion-token',status)

    def test_pagination_and_ssrf(self):
        cursor = 'https://api.figma.com/v1/files/ABC123/versions?before=10'
        with patch.object(service,'fetch_json',side_effect=[{**FIGMA,'pagination':{'next_page':cursor}},CURRENT]):
            result = service.sync_external(self.db,self.project,'figma')
        self.assertTrue(result['has_next'])
        self.assertEqual(result['next_cursor'],cursor)
        with patch.object(service,'fetch_json',return_value={'versions':[],'pagination':{}}) as get:
            result = service.sync_external(self.db,self.project,'figma',cursor)
            self.assertEqual(get.call_args.args[1],cursor)
            self.assertEqual(get.call_count,1)
            self.assertFalse(result['has_next'])
        for bad in ['https://evil.com/', 'https://api.figma.com/v1/files/OTHER/versions', 'https://api.figma.com:443/v1/files/ABC123/versions']:
            with patch.object(service,'fetch_json') as get, self.assertRaises(HTTPException):
                service.sync_external(self.db,self.project,'figma',bad)
            get.assert_not_called()

    def test_malformed_and_failed_responses_do_not_write(self):
        for data in ({}, {**NOTION,'last_edited_time':'bad'}, {**NOTION,'id':'b'*32}):
            with self.assertRaises(HTTPException) as e:
                self.sync_notion(data)
            self.assertEqual(e.exception.status_code,502)
        with patch.object(service,'fetch_json',side_effect=HTTPException(503,'limited')):
            with self.assertRaises(HTTPException):
                service.sync_external(self.db,self.project,'figma')
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProjectActivity)),0)

    def test_http_errors_and_safe_headers(self):
        for code,expected in [(401,502),(403,502),(404,404),(429,503),(500,502),(302,502)]:
            with patch('httpx.Client.get',return_value=httpx.Response(code,headers={'Retry-After':'30'},text='private-token')):
                with self.assertRaises(HTTPException) as e:
                    service.fetch_json('figma','https://api.figma.com/v1/files/ABC123',{})
            self.assertEqual(e.exception.status_code,expected)
            self.assertNotIn('private-token',str(e.exception.detail))
            if code == 429:
                self.assertEqual(e.exception.headers,{'Retry-After':'30'})
        for exception,code in [(httpx.ReadTimeout('secret'),504),(httpx.ConnectError('secret'),502)]:
            with patch('httpx.Client.get',side_effect=exception), self.assertRaises(HTTPException) as e:
                service.fetch_json('notion','https://api.notion.com/v1/pages/'+PAGE,{})
            self.assertEqual(e.exception.status_code,code)
        with patch('httpx.Client.get',return_value=httpx.Response(200,text='bad')), self.assertRaises(HTTPException):
            service.fetch_json('notion','https://api.notion.com/v1/pages/'+PAGE,{})

    def test_project_save_queues_initial_collection(self):
        user=SimpleNamespace(id=self.project.owner_id)
        tasks=BackgroundTasks()
        created=project_routes.create_project(ProjectCreate(project_name='New',figma_url=self.project.figma_url),tasks,self.db,user)
        self.assertEqual(tasks.tasks[0].args,(created.id,user.id,('figma',)))
        tasks=BackgroundTasks()
        project_routes.update_project(ProjectUpdate(notion_url=self.project.notion_url),tasks,self.project.id,self.db,user)
        self.assertEqual(tasks.tasks[0].args,(self.project.id,user.id,('notion',)))
        tasks=BackgroundTasks()
        project_routes.update_project(ProjectUpdate(project_name='Rename'),tasks,self.project.id,self.db,user)
        self.assertEqual(tasks.tasks,[])
        paths=app.openapi()['paths']
        for source in ('figma','notion'):
            self.assertIn('post',paths['/api/projects/{project_id}/'+source+'/sync'])
        self.assertIn('get',paths['/api/projects/{project_id}/integrations'])

    def test_initial_sync_uses_new_session_and_handles_failure(self):
        with patch('app.services.initial_sync.SessionLocal') as factory, patch('app.services.initial_sync.sync_external') as sync:
            factory.return_value.__enter__.return_value.get.return_value=self.project
            sync.side_effect=HTTPException(503,'Unavailable')
            initial_sync(self.project.id,self.project.owner_id,('figma','notion'))
            self.assertEqual(sync.call_count,2)
            sync.reset_mock()
            initial_sync(self.project.id,999,('figma',))
            sync.assert_not_called()
