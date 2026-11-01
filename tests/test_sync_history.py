import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select, func, inspect
from app.models.project_activity import ProjectActivity
from app.models.project_sync_run import ProjectSyncRun
from app.services.github_sync import sync_commits
from app.services.external_sync import sync_external
from app.services.project_github import GitHubClient
from app.routers.project_sync_runs import list_runs, SyncRun
from scripts.setup_sync_runs_db import setup
from test_dashboard_database import DashboardDatabaseTests
from test_project_github import COMMIT


class SyncHistoryTests(unittest.TestCase):
    setUp = DashboardDatabaseTests.setUp
    tearDown = DashboardDatabaseTests.tearDown

    def runs(self):
        return self.db.scalars(select(ProjectSyncRun).order_by(ProjectSyncRun.id)).all()

    def sync(self, items):
        with patch.object(GitHubClient, 'get', return_value=(items, False)):
            return sync_commits(self.db, self.project, 'main', 1, 100)

    def test_success_duplicates_and_empty_are_separate_runs(self):
        self.sync([COMMIT])
        self.sync([COMMIT])
        self.sync([])
        runs = self.runs()
        self.assertEqual([(r.fetched, r.created, r.existing) for r in runs], [(1,1,0),(1,0,1),(0,0,0)])
        for run in runs:
            self.assertEqual(run.status, 'success')
            self.assertGreaterEqual(run.finished_at, run.started_at)
            SyncRun.model_validate(run)

    def test_upstream_failure_is_recorded_without_secret(self):
        error = HTTPException(504, 'private-token-example')
        with patch.object(GitHubClient, 'get', side_effect=error):
            with self.assertRaises(HTTPException) as caught:
                sync_commits(self.db, self.project, None, 1, 100)
        self.assertIs(caught.exception, error)
        run = self.runs()[0]
        self.assertEqual((run.status, run.error_code, run.created), ('failed',504,0))
        self.assertNotIn('private-token', run.error_message)

    def test_partial_activity_failure_rolls_back_but_keeps_history(self):
        broken = copy.deepcopy(COMMIT)
        broken['sha'] = 'broken'
        broken['commit']['committer'] = {}
        broken['commit']['author'] = {}
        with self.assertRaises(HTTPException):
            self.sync([COMMIT, broken])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProjectActivity)), 0)
        run = self.runs()[0]
        self.assertEqual((run.status, run.fetched, run.created), ('failed',2,0))

    def test_external_services_success_and_failure(self):
        for source in ('figma', 'notion'):
            with patch('app.services.external_sync.collect_'+source, return_value=([], None)):
                sync_external(self.db, self.project, source)
            with patch('app.services.external_sync.collect_'+source, side_effect=HTTPException(403, 'secret')):
                with self.assertRaises(HTTPException):
                    sync_external(self.db, self.project, source)
        self.assertEqual([(r.source,r.status) for r in self.runs()], [('figma','success'),('figma','failed'),('notion','success'),('notion','failed')])
        rows = list_runs(source='notion', status='failed', limit=1, offset=0, project=self.project, db=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source, 'notion')
        self.assertEqual(list_runs(source=None, status=None, limit=50, offset=0, project=self.other, db=self.db), [])

    def test_migration_only_creates_history_table_and_is_repeatable(self):
        ProjectSyncRun.__table__.drop(self.engine)
        with self.engine.connect() as connection:
            setup(connection)
            self.assertFalse(inspect(connection).has_table('project_sync_runs'))
            setup(connection, True)
            setup(connection, True)
        self.db.expire_all()
        self.assertEqual(self.project.project_name, 'One')
