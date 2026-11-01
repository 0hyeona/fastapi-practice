import os
import unittest
from unittest.mock import patch
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from app.main import app
from app.routers import project_connections as routes
from app.routers.project_github import project_activities
from app.schemas.project import ProjectResponse
from app.schemas.project_activity import ProjectActivityCreate
from app.models.project_activity import ProjectActivity
from app.services import project_content_service as content
import test_dashboard_database


class ConnectionsTests(unittest.TestCase):
    setUp = test_dashboard_database.DashboardDatabaseTests.setUp
    tearDown = test_dashboard_database.DashboardDatabaseTests.tearDown

    def test_registered_url_is_not_verified_access(self):
        self.project.figma_url='https://www.figma.com/design/ABC/Test'
        self.db.commit()
        with patch.dict(os.environ, {'FIGMA_TOKEN':'','GITHUB_TOKEN':''}):
            result=routes.Connections.model_validate(routes.connections(self.project,self.db))
        self.assertEqual([c.source for c in result.connections],['github','notion','figma'])
        self.assertEqual(result.connections[0].connection_status,'public_access_unverified')
        self.assertEqual(result.connections[1].connection_status,'not_linked')
        self.assertEqual(result.connections[2].connection_status,'configuration_required')
        self.assertEqual(result.connections[2].external_id,'ABC')
        self.assertTrue(all(not c.access_verified for c in result.connections))
        self.assertEqual(ProjectResponse.model_validate(routes.project_detail(self.project)).id,self.project.id)

    def test_register_replace_unlink_without_deleting_activities(self):
        for url in ('https://www.figma.com/design/ABC/Test','https://www.figma.com/design/DEF/Test',None):
            tasks=BackgroundTasks()
            routes.save_connection(routes.ConnectionUpdate(external_url=url),'figma',tasks,self.project,self.db)
            self.assertEqual(self.project.figma_url,url)
            self.assertEqual(len(tasks.tasks),int(url is not None))
        with self.assertRaises(HTTPException):
            routes.save_connection(routes.ConnectionUpdate(external_url='https://evil.com/file/ABC/Test'),'figma',BackgroundTasks(),self.project,self.db)
        self.assertIsNone(self.project.figma_url)
        with self.assertRaises(ValidationError):
            routes.ConnectionUpdate()

    def test_counts_and_source_filters_are_project_scoped(self):
        for source in ('github','notion','figma'):
            content.create(self.db,ProjectActivity,ProjectActivityCreate(project_id=self.project.id,source=source,
                activity_type='edit',title=source,occurred_at='2026-11-01T00:00:00Z'),self.project.owner_id)
        content.create(self.db,ProjectActivity,ProjectActivityCreate(project_id=self.other.id,source='figma',
            activity_type='edit',title='other',occurred_at='2026-11-01T00:00:00Z'),self.other.owner_id)
        for source in ('github','notion','figma'):
            rows=project_activities(self.project,self.db,True,source,50,0)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0].source,source)
        result=routes.Connections.model_validate(routes.connections(self.project,self.db))
        self.assertEqual([c.unorganized_count for c in result.connections],[1,1,1])
        routes.save_connection(routes.ConnectionUpdate(external_url=None),'github',BackgroundTasks(),self.project,self.db)
        self.assertEqual(len(project_activities(self.project,self.db,True,'github',50,0)),1)
        self.assertTrue(all(c.last_activity_stored_at for c in result.connections))

    def test_openapi_routes_share_ownership_dependency(self):
        paths=app.openapi()['paths']
        for path in ('/api/projects/{project_id}','/api/projects/{project_id}/connections'):
            self.assertIn('get',paths[path])
            self.assertTrue(paths[path]['get']['security'])
        patch_route=paths['/api/projects/{project_id}/connections/{source}']['patch']
        self.assertTrue(patch_route['security'])
        self.assertEqual(next(p for p in patch_route['parameters'] if p['name']=='source')['schema']['enum'],['github','figma','notion'])
