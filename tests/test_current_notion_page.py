from datetime import datetime
from uuid import UUID
import unittest

from sqlalchemy import func, select
from app.models.project_activity import ProjectActivity
from app.routers import project_github, project_connections
from app.services import project_content_service as content
import test_project_access


class CurrentNotionPageTests(unittest.TestCase):
    def setUp(self):
        test_project_access.ProjectAccessTests.setUp(self)
        self.project.github_url = None
        self.a, self.b = 'a' * 32, 'b' * 32
        self.project.notion_url = 'https://app.notion.com/team/Page-' + self.a + '?source=copy_link'
        for source, url, title, day in [
            ('notion', 'https://www.notion.so/' + self.a, 'A', 1),
            ('notion', 'https://www.notion.so/' + self.b, 'B', 3),
            ('notion', None, 'Unknown page', 4),
            ('github', None, 'Commit', 2),
        ]:
            self.db.add(ProjectActivity(project_id=self.project.id, source=source,
                                       source_url=url, title=title, activity_type='edit',
                                       occurred_at=datetime(2026, 11, day)))
        self.db.commit()

    def tearDown(self):
        test_project_access.ProjectAccessTests.tearDown(self)

    def titles(self, project_id=None, limit=50, offset=0, user_id=None):
        return [row.title for row in content.list_records(
            self.db, ProjectActivity, user_id or self.project.owner_id, project_id,
            limit, offset, ProjectActivity.occurred_at)]

    def test_switch_and_disconnect_filter_lists_counts_and_recent_items(self):
        self.assertEqual(self.titles(self.project.id), ['Commit', 'A'])
        self.assertEqual(self.titles(limit=1, offset=1), ['A'])
        self.assertEqual(project_github.dashboard(self.project, self.db)['unorganized_counts']['notion'], 1)
        connections = project_connections.connections(self.project, self.db)['connections']
        self.assertEqual(next(c for c in connections if c['source'] == 'notion')['unorganized_count'], 1)

        self.project.notion_url = 'https://www.notion.so/Other-' + str(UUID(self.b)).upper() + '/?x=1#section'
        self.db.commit()
        self.assertEqual(self.titles(), ['B', 'Commit'])
        result = project_github.dashboard(self.project, self.db)
        self.assertEqual([row.title for row in result['recent_activities']], ['B', 'Commit'])
        self.assertEqual(result['unorganized_counts']['total'], 2)

        self.project.notion_url = None
        self.db.commit()
        self.assertEqual(self.titles(), ['Commit'])
        self.assertEqual(project_github.dashboard(self.project, self.db)['unorganized_counts']['notion'], 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProjectActivity)), 4)

    def test_shared_member_and_each_project_use_their_own_page(self):
        test_project_access.ProjectAccessTests.add(self)
        self.other.notion_url = 'https://www.notion.so/' + self.b
        self.db.add(ProjectActivity(project_id=self.other.id, source='notion',
                                   source_url='https://www.notion.so/' + self.b,
                                   title='Other project B', activity_type='edit',
                                   occurred_at=datetime(2026, 11, 5)))
        self.db.commit()
        self.assertEqual(self.titles(), ['Other project B', 'Commit', 'A'])
        self.assertEqual(self.titles(user_id=self.member.id), ['Commit', 'A'])
