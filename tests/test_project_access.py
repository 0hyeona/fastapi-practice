"""Database/auth dependency coverage runnable without local network sockets."""
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.models.user import User
from app.models.project_member import ProjectMember
from app.models.story import Story
from app.models.project_activity import ProjectActivity
from app.schemas.story import StoryCreate, StoryUpdate
from app.services import project_service, project_content_service as content, external_sync
from app.routers import project_github, project_members, project_integrations, project_connections, project_sync_runs
from app.main import app
from scripts.setup_project_members_db import setup
import test_dashboard_database
from test_external_sync import NOTION, PAGE


class ProjectAccessTests(unittest.TestCase):
    def setUp(self):
        test_dashboard_database.DashboardDatabaseTests.setUp(self)
        self.member = User(user_id='member', name='Member', email='member@example.com', password_hash='unused')
        self.stranger = User(user_id='stranger', name='Stranger', email='stranger@example.com', password_hash='unused')
        self.db.add_all([self.member, self.stranger])
        self.project.github_url = None
        self.db.commit()
        self.story = content.create(self.db, Story, StoryCreate(project_id=self.project.id, title='Shared'), self.project.owner_id)

    def tearDown(self):
        test_dashboard_database.DashboardDatabaseTests.tearDown(self)

    def add(self):
        return project_members.add_member(project_members.MemberAdd(email=self.member.email), self.project, self.db)

    def test_members_read_shared_lists_details_and_dashboard_only(self):
        self.add()
        self.assertEqual([p.id for p in project_service.list_projects(self.db, self.member.id, 50, 0)], [self.project.id])
        project = project_github.accessible_project(self.project.id, self.db, self.member)
        self.assertEqual(project.id, self.project.id)
        self.assertEqual(content.get(self.db, Story, self.story.id, self.member.id, shared=True).id, self.story.id)
        self.assertEqual(len(content.list_records(self.db, Story, self.member.id, None, 50, 0, Story.created_at)), 1)
        self.assertEqual(len(project_github.dashboard(project, self.db)['recent_stories']), 1)
        access = project_members.access(project, self.member)
        self.assertEqual(access['role'], 'member')
        self.assertFalse(access['can_manage'])
        self.assertEqual(access['notion_connection_owner_id'], self.project.owner_id)
        for project_id, user in [(self.other.id, self.member), (self.project.id, self.stranger)]:
            with self.assertRaises(HTTPException):
                project_github.accessible_project(project_id, self.db, user)

    def test_members_cannot_write_or_pass_owner_dependencies(self):
        self.add()
        with self.assertRaises(HTTPException):
            project_github.owned_project(self.project.id, self.db, self.member)
        for action in [
            lambda: content.update(self.db, Story, self.story.id, self.member.id, StoryUpdate(title='No')),
            lambda: content.delete(self.db, Story, self.story.id, self.member.id),
            lambda: content.create(self.db, Story, StoryCreate(project_id=self.project.id, title='No'), self.member.id),
        ]:
            with self.assertRaises(HTTPException):
                action()
        self.assertIsNone(project_service.set_project_status(self.db, self.project.id, self.member.id, 'archived'))
        self.assertFalse(project_service.delete_project(self.db, self.project.id, self.member.id))
        self.assertEqual(self.story.title, 'Shared')

    def test_shared_github_reads_use_owner_encrypted_credentials(self):
        import os
        from cryptography.fernet import Fernet
        from app.models.github_account import GithubAccount
        from app.services.project_github import GitHubClient
        from test_project_github import REPO

        self.add()
        self.project.github_url = 'https://github.com/acme/demo'
        key = Fernet.generate_key()
        cipher = Fernet(key)
        for github_id, user_id, token in [
            (101, self.project.owner_id, 'owner-token'),
            (102, self.member.id, 'member-token'),
        ]:
            self.db.add(GithubAccount(github_id=github_id, user_id=user_id,
                                     token_ciphertext=cipher.encrypt(token.encode()).decode()))
        self.db.commit()
        project = project_github.accessible_project(self.project.id, self.db, self.member)
        with patch.dict(os.environ, {'GITHUB_CREDENTIAL_ENCRYPTION_KEY': key.decode()}):
            client = project_github.github_client(project, self.db)
            self.assertEqual(client.headers['Authorization'], 'Bearer owner-token')

            seen_headers = []
            def get(client, *args, **kwargs):
                seen_headers.append(client.headers['Authorization'])
                return (REPO, False) if len(seen_headers) == 1 else ([], False)

            with patch.object(GitHubClient, 'get', get):
                result = project_github.dashboard(project, self.db)
            self.assertEqual(result['github']['full_name'], 'acme/demo')
            self.assertEqual(seen_headers, ['Bearer owner-token', 'Bearer owner-token'])

    def test_revocation_removes_all_read_and_sync_access(self):
        self.add()
        project_members.remove_member(self.member.id, self.project, self.db)
        self.assertEqual(project_service.list_projects(self.db, self.member.id, 50, 0), [])
        self.assertEqual(content.list_records(self.db, Story, self.member.id, None, 50, 0, Story.created_at), [])
        with self.assertRaises(HTTPException):
            content.get(self.db, Story, self.story.id, self.member.id, shared=True)
        with self.assertRaises(HTTPException), patch.object(external_sync, 'fetch_json') as provider:
            project_github.accessible_project(self.project.id, self.db, self.member)
        provider.assert_not_called()

    def test_shared_notion_sync_uses_owner_and_records_changes(self):
        self.add()
        self.project.notion_url = 'https://www.notion.so/' + PAGE
        self.db.commit()
        project = project_github.accessible_project(self.project.id, self.db, self.member)
        empty = {'object': 'list', 'results': [], 'has_more': False}
        changed = {**NOTION, 'properties': {'Name': {'type': 'title', 'title': [{'plain_text': 'Changed'}]}}}
        with patch('app.services.notion_oauth.user_token', return_value='owner-secret') as token, \
                patch.object(external_sync, 'fetch_json', side_effect=[NOTION, empty, NOTION, changed, empty, changed]) as provider:
            self.assertEqual(project_integrations.sync_notion(project, self.db)['created'], 0)
            self.assertEqual(project_integrations.sync_notion(project, self.db)['created'], 1)
            self.assertTrue(all(call.args[1] == self.project.owner_id for call in token.call_args_list))
            self.assertTrue(all(call.args[2]['Authorization'] == 'Bearer owner-secret' for call in provider.call_args_list))
        records = content.list_records(self.db, ProjectActivity, self.member.id, self.project.id, 50, 0, ProjectActivity.occurred_at)
        self.assertEqual(len(records), 1)
        self.assertNotIn('owner-secret', records[0].description)

    def test_membership_is_idempotent_owner_not_redundant_and_cascades(self):
        first = self.add()
        self.assertEqual(self.add(), first)
        self.assertEqual(len(project_members.members(self.project, self.db)), 1)
        owner = self.db.get(User, self.project.owner_id)
        with self.assertRaises(HTTPException):
            project_members.add_member(project_members.MemberAdd(email=owner.email), self.project, self.db)
        with self.assertRaises(HTTPException):
            project_members.add_member(project_members.MemberAdd(email='unknown@example.com'), self.project, self.db)
        project_service.delete_project(self.db, self.project.id, self.project.owner_id)
        self.assertEqual(self.db.scalars(select(ProjectMember)).all(), [])

    def test_multiple_members_and_membership_in_multiple_projects(self):
        self.add()
        project_members.add_member(project_members.MemberAdd(email=self.stranger.email), self.project, self.db)
        project_members.add_member(project_members.MemberAdd(email=self.member.email), self.other, self.db)
        self.assertEqual({row['user_id'] for row in project_members.members(self.project, self.db)},
                         {self.member.id, self.stranger.id})
        self.assertEqual({p.id for p in project_service.list_projects(self.db, self.member.id, 50, 0)},
                         {self.project.id, self.other.id})
        project_members.remove_member(self.member.id, self.project, self.db)
        self.assertEqual([p.id for p in project_service.list_projects(self.db, self.member.id, 50, 0)],
                         [self.other.id])
        self.assertEqual(project_github.accessible_project(self.project.id, self.db, self.stranger).id,
                         self.project.id)

    def test_table_setup_is_repeatable_and_only_creates_memberships(self):
        with self.engine.connect() as connection:
            ProjectMember.__table__.drop(connection)
            connection.commit()
            before = set(inspect(connection).get_table_names())
            setup(connection)
            self.assertEqual(set(inspect(connection).get_table_names()), before)
            setup(connection, apply=True)
            setup(connection, apply=True)
            self.assertEqual(set(inspect(connection).get_table_names()), before | {'project_members'})

    def test_http_routes_use_shared_reads_and_owner_only_management(self):
        expected = {
            ('GET', '/api/projects/{project_id}/dashboard'): project_github.accessible_project,
            ('GET', '/api/projects/{project_id}/connections'): project_github.accessible_project,
            ('GET', '/api/projects/{project_id}/activities'): project_github.accessible_project,
            ('GET', '/api/projects/{project_id}/stories'): project_github.accessible_project,
            ('GET', '/api/projects/{project_id}/sync-runs'): project_github.accessible_project,
            ('POST', '/api/projects/{project_id}/notion/sync'): project_github.accessible_project,
            ('POST', '/api/projects/{project_id}/members'): project_github.owned_project,
            ('DELETE', '/api/projects/{project_id}/members/{user_id}'): project_github.owned_project,
            ('PATCH', '/api/projects/{project_id}/connections/{source}'): project_github.owned_project,
        }
        routes = [route for router in (project_github.router, project_members.router,
                  project_integrations.router, project_connections.router, project_sync_runs.router)
                  for route in router.routes]
        paths = app.openapi()['paths']
        for (method, path), dependency in expected.items():
            with self.subTest(method=method, path=path):
                self.assertIn(method.lower(), paths[path])
                route = next(r for r in routes if r.path == path and method in r.methods)
                self.assertIn(dependency, [d.call for d in route.dependant.dependencies])
