from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.database.database import Base
from app.main import app
from app.models.user import User
from app.models.project import Project
from app.models.story import Story
from app.models.project_activity import ProjectActivity
from app.schemas.project_activity import ProjectActivityCreate, ProjectActivityUpdate
from app.schemas.project_github import Dashboard
from app.services import project_content_service as content
from app.services.github_sync import sync_commits
from app.services.project_github import GitHubClient
from app.routers import project_github as routes
from test_project_github import COMMIT


class DashboardDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        with self.engine.connect() as c:
            c.exec_driver_sql('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        user = User(user_id='one', name='One', email='one@example.com', password_hash='unused')
        self.db.add(user)
        self.db.flush()
        self.project = Project(owner_id=user.id, project_name='One', github_url='https://github.com/acme/demo')
        self.other = Project(owner_id=user.id, project_name='Other')
        self.db.add_all([self.project, self.other])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def story(self, project=None):
        row = Story(project_id=(project or self.project).id, title='Story', content='')
        self.db.add(row)
        self.db.commit()
        return row

    def dashboard(self):
        with patch.object(GitHubClient, 'get', side_effect=HTTPException(503, 'Unavailable')):
            return Dashboard.model_validate(routes.dashboard(self.project, self.db))

    def sync(self, items=None, branch='main'):
        with patch.object(GitHubClient, 'get', return_value=([COMMIT] if items is None else items, True)):
            return sync_commits(self.db, self.project, branch, 1, 100)

    def test_sync_idempotency_link_unlink_and_story_delete(self):
        self.assertEqual(self.sync()['created'], 1)
        self.assertEqual(self.sync(branch='feature')['created'], 0)
        activity = self.db.scalar(select(ProjectActivity))
        self.assertEqual(activity.branch_name, 'main')
        self.assertEqual(self.dashboard().unorganized_counts.github, 1)
        story = self.story()
        content.update(self.db, ProjectActivity, activity.id, self.project.owner_id, ProjectActivityUpdate(story_id=story.id))
        self.assertEqual(self.dashboard().unorganized_counts.total, 0)
        self.sync()
        self.assertEqual(activity.story_id, story.id)
        content.update(self.db, ProjectActivity, activity.id, self.project.owner_id, ProjectActivityUpdate(story_id=None))
        self.assertEqual(self.dashboard().unorganized_counts.total, 1)
        content.update(self.db, ProjectActivity, activity.id, self.project.owner_id, ProjectActivityUpdate(story_id=story.id))
        content.delete(self.db, Story, story.id, self.project.owner_id)
        self.db.expire_all()
        self.assertIsNone(activity.story_id)
        self.assertEqual(self.dashboard().unorganized_counts.total, 1)

    def test_cross_project_link_is_rejected(self):
        self.sync()
        activity = self.db.scalar(select(ProjectActivity))
        other_story = self.story(self.other)
        with self.assertRaises(HTTPException) as error:
            content.update(self.db, ProjectActivity, activity.id, self.project.owner_id, ProjectActivityUpdate(story_id=other_story.id))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            content.create(self.db, ProjectActivity, ProjectActivityCreate(project_id=self.project.id,
                story_id=other_story.id, source='figma', activity_type='edit',title='x',occurred_at='2026-11-01T00:00:00Z'), self.project.owner_id)
        with self.assertRaises(HTTPException):
            content.update(self.db, ProjectActivity, activity.id, self.project.owner_id, ProjectActivityUpdate(source='figma'))

    def test_all_counts_order_filters_and_project_isolation(self):
        for i in range(4):
            row = self.story()
            row.title = str(i)
            row.created_at = datetime(2026, 11, 1)
        self.story(self.other)
        for source, project in [('figma', self.project), ('notion', self.project), ('github', self.other)]:
            self.db.add(ProjectActivity(project_id=project.id,source=source,activity_type='edit',title='x',occurred_at=datetime(2026,11,1)))
        self.db.commit()
        self.sync()
        result = self.dashboard()
        self.assertEqual(result.unorganized_counts.model_dump(), {'github':1,'figma':1,'notion':1,'total':3})
        self.assertEqual([s.title for s in result.recent_stories], ['3','2','1'])
        self.assertEqual(result.github_error, 'Unavailable')
        items = routes.project_activities(self.project,self.db,True,'github',50,0)
        self.assertEqual(len(items),1)
        self.assertEqual(routes.project_activities(self.project,self.db,False,None,50,0),[])
        self.assertEqual(len(routes.project_stories(self.project,self.db,None,3,0)),3)
        self.project.github_url = None
        self.db.commit()
        result = Dashboard.model_validate(routes.dashboard(self.project,self.db))
        self.assertIsNone(result.github)
        self.assertEqual(result.unorganized_counts.total,3)

    def test_failed_import_rolls_back_and_empty_import(self):
        broken = {**COMMIT, 'sha':'b'*40, 'commit':{'message':'bad','author':None}}
        with self.assertRaises(HTTPException):
            self.sync([COMMIT, broken])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProjectActivity)), 0)
        self.assertEqual(self.sync([])['fetched'],0)
        with patch.object(GitHubClient,'get',side_effect=HTTPException(502,'offline')):
            with self.assertRaises(HTTPException):
                sync_commits(self.db,self.project,None,1,100)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProjectActivity)), 0)

    def test_openapi_paths_and_ownership(self):
        paths = app.openapi()['paths']
        for suffix in ['dashboard','activities','stories','github/commits','github/branches']:
            self.assertIn('get',paths['/api/projects/{project_id}/'+suffix])
        self.assertIn('post',paths['/api/projects/{project_id}/github/sync'])
        with self.assertRaises(HTTPException) as error:
            routes.owned_project(self.project.id,self.db,SimpleNamespace(id=999))
        self.assertEqual(error.exception.status_code,404)
