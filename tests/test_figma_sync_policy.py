import os
import unittest
from datetime import timedelta
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select
from app.models.project_sync_run import ProjectSyncRun
from app.services.figma_sync_policy import now, state
from app.services.sync_history import record_sync
from test_dashboard_database import DashboardDatabaseTests


class FigmaPolicyTests(unittest.TestCase):
    setUp = DashboardDatabaseTests.setUp
    tearDown = DashboardDatabaseTests.tearDown

    def test_rate_limit_survives_session_reload_and_blocks_network(self):
        with self.assertRaises(HTTPException):
            record_sync(self.db, self.project, 'figma', lambda _: (_ for _ in ()).throw(
                HTTPException(429, 'secret', headers={'Retry-After': '86400'})))
        self.db.expire_all()
        run = self.db.scalar(select(ProjectSyncRun))
        self.assertEqual(run.status, 'failed')
        self.assertNotIn('secret', run.error_message)
        self.assertGreater(state(self.db, self.project.id)['retry_after_seconds'], 86390)
        with patch('app.services.external_sync.collect_figma') as collect:
            from app.services.external_sync import sync_external
            with self.assertRaises(HTTPException) as error:
                sync_external(self.db, self.project, 'figma')
            self.assertEqual(error.exception.status_code, 429)
            collect.assert_not_called()

    def test_running_run_blocks_another_request(self):
        self.db.add(ProjectSyncRun(project_id=self.project.id, source='figma',
                                   status='running', started_at=now()))
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            record_sync(self.db, self.project, 'figma', lambda _: self.fail('must not collect'))
        self.assertEqual(error.exception.status_code, 409)

    def test_success_interval_and_pagination(self):
        result = {'fetched': 0, 'created': 0, 'existing': 0}
        with patch.dict(os.environ, {'FIGMA_SYNC_MIN_INTERVAL_SECONDS': '600'}):
            record_sync(self.db, self.project, 'figma', lambda _: result)
            with self.assertRaises(HTTPException):
                record_sync(self.db, self.project, 'figma', lambda _: self.fail('blocked'))
            with self.assertRaises(HTTPException):
                record_sync(self.db, self.project, 'figma', lambda _: result, pagination=True)
            runs = self.db.scalars(select(ProjectSyncRun)).all()
            for run in runs:
                run.finished_at = now() - timedelta(minutes=11)
            self.db.commit()
            self.assertTrue(state(self.db, self.project.id)['can_sync'])

    def test_rate_failure_keeps_cached_activity(self):
        from app.services.external_sync import sync_external
        from app.models.project_activity import ProjectActivity
        self.db.add(ProjectActivity(project_id=self.project.id, source='figma',
                    title='Cached design', activity_type='file_version', occurred_at=now(), external_id='cached'))
        self.db.commit()
        with patch('app.services.external_sync.collect_figma', side_effect=HTTPException(429, 'limited')):
            with self.assertRaises(HTTPException):
                sync_external(self.db, self.project, 'figma')
        self.assertEqual(self.db.scalar(select(ProjectActivity)).title, 'Cached design')
