"""Exercise sharing across actual HTTP auth, membership, reads and Notion sync."""
import unittest
from unittest.mock import patch
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
import test_projects
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_activity import ProjectActivity
from app.services import external_sync
from scripts.setup_project_members_db import setup
from test_external_sync import NOTION, PAGE


class ProjectSharingTests(unittest.TestCase):
    def setUp(self):
        test_projects.ProjectTests.setUp(self)
        with self.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        self.member_id, self.member_headers = self.account('member')
        self.stranger_id, self.stranger_headers = self.account('stranger')
        self.project_id = self.client.post('/projects', json=self.project, headers=self.headers).json()['id']
        self.other_id = self.client.post('/projects', json=self.project, headers=self.headers).json()['id']
        self.base = f'/api/projects/{self.project_id}'
        story = self.client.post('/stories', headers=self.headers,
                                 json={'project_id': self.project_id, 'title': 'Shared story', 'content': 'Notes'}).json()
        self.story_url = f"/stories/{story['id']}"
        activity = self.client.post('/project_activities', headers=self.headers, json={
            'project_id': self.project_id, 'source': 'notion', 'title': 'Edited',
            'occurred_at': '2026-11-20T00:00:00Z'}).json()
        self.activity_url = f"/project_activities/{activity['activity_id']}"

    def tearDown(self):
        test_projects.ProjectTests.tearDown(self)

    def account(self, name):
        payload = {**self.payload, 'user_id': name, 'email': name + '@example.com'}
        self.client.post('/api/auth/signup', json=payload)
        login = self.client.post('/api/auth/login', json={
            'email': payload['email'], 'password': payload['password']}).json()
        return login['user']['id'], {'Authorization': 'Bearer ' + login['access_token']}

    def add(self):
        result = self.client.post(self.base + '/members', headers=self.headers,
                                  json={'email': 'member@example.com'})
        self.assertEqual(result.status_code, 200, result.text)
        return result

    def read_urls(self):
        return [f'/projects/{self.project_id}', self.base, self.base + '/access',
                self.base + '/dashboard', self.base + '/activities', self.base + '/stories',
                self.base + '/connections', self.base + '/integrations', self.base + '/sync-runs',
                self.story_url, self.story_url + '/export', self.activity_url,
                f'/stories?project_id={self.project_id}',
                f'/project_activities?project_id={self.project_id}']

    def test_member_reads_shared_project_without_own_notion_connection(self):
        self.add()
        for url in self.read_urls():
            with self.subTest(url=url):
                result = self.client.get(url, headers=self.member_headers)
                self.assertEqual(result.status_code, 200, result.text)
        self.assertFalse(self.client.get('/api/integrations/notion', headers=self.member_headers).json()['connected'])
        access = self.client.get(self.base + '/access', headers=self.member_headers).json()
        self.assertEqual(access['role'], 'member')
        self.assertFalse(access['can_manage'])
        self.assertEqual(access['notion_connection_owner_id'], self.owner_id)
        self.assertEqual([p['id'] for p in self.client.get('/projects', headers=self.member_headers).json()], [self.project_id])
        self.assertEqual(len(self.client.get('/stories', headers=self.member_headers).json()), 1)
        self.assertEqual(len(self.client.get('/project_activities', headers=self.member_headers).json()), 1)
        self.assertEqual(self.client.get(f'/projects/{self.other_id}', headers=self.member_headers).status_code, 404)

    def test_nonmembers_and_revoked_members_are_denied_before_provider_calls(self):
        self.add()
        self.assertEqual(self.client.delete(self.base + f'/members/{self.member_id}', headers=self.headers).status_code, 204)
        with patch.object(external_sync, 'fetch_json') as provider:
            for headers in (self.member_headers, self.stranger_headers):
                for url in self.read_urls():
                    with self.subTest(url=url):
                        self.assertEqual(self.client.get(url, headers=headers).status_code, 404)
                self.assertEqual(self.client.get('/projects', headers=headers).json(), [])
                self.assertEqual(self.client.get('/stories', headers=headers).json(), [])
                self.assertEqual(self.client.get('/project_activities', headers=headers).json(), [])
                self.assertEqual(self.client.post(self.base + '/notion/sync', headers=headers).status_code, 404)
            provider.assert_not_called()

    def test_member_cannot_manage_members_connections_or_edit_records(self):
        self.add()
        attempts = [
            ('post', self.base + '/members', {'email': 'stranger@example.com'}),
            ('delete', self.base + f'/members/{self.member_id}', None),
            ('patch', self.base + '/connections/notion', {'external_url': None}),
            ('patch', f'/projects/{self.project_id}', {'project_name': 'Stolen'}),
            ('patch', f'/projects/{self.project_id}/archive', None),
            ('patch', f'/projects/{self.project_id}/restore', None),
            ('delete', f'/projects/{self.project_id}', None),
            ('post', '/stories', {'project_id': self.project_id, 'title': 'Not allowed'}),
            ('patch', self.story_url, {'title': 'Changed'}),
            ('delete', self.story_url, None),
            ('patch', self.activity_url, {'title': 'Changed'}),
            ('delete', self.activity_url, None),
            ('post', self.base + '/figma/sync', None),
            ('post', self.base + '/github/sync', None),
        ]
        for method, url, payload in attempts:
            with self.subTest(method=method, url=url):
                result = self.client.request(method, url, headers=self.member_headers,
                                             **({'json': payload} if payload is not None else {}))
                self.assertEqual(result.status_code, 404, result.text)
        self.assertEqual(self.client.get(self.base + '/members', headers=self.member_headers).status_code, 404)

    def test_member_sync_uses_owner_credentials_and_changes_are_shared(self):
        self.add()
        with Session(self.engine) as db:
            db.get(Project, self.project_id).notion_url = 'https://www.notion.so/' + PAGE
            db.commit()
        empty = {'object': 'list', 'results': [], 'has_more': False}
        changed = {**NOTION, 'properties': {'Name': {'type': 'title', 'title': [{'plain_text': 'Changed notes'}]}}}
        with patch('app.services.notion_oauth.user_token', return_value='owner-only-secret') as token, \
                patch.object(external_sync, 'fetch_json', side_effect=[NOTION, empty, NOTION, changed, empty, changed]) as provider:
            first = self.client.post(self.base + '/notion/sync', headers=self.member_headers)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['created'], 0)
            second = self.client.post(self.base + '/notion/sync', headers=self.member_headers)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()['created'], 1)
            self.assertTrue(all(call.args[1] == self.owner_id for call in token.call_args_list))
            self.assertTrue(all(call.args[2]['Authorization'] == 'Bearer owner-only-secret' for call in provider.call_args_list))
            self.assertNotIn('owner-only-secret', first.text + second.text)
        url = self.base + '/activities?source=notion'
        shared = self.client.get(url, headers=self.member_headers)
        self.assertEqual(shared.json(), self.client.get(url, headers=self.headers).json())
        self.assertEqual(len(shared.json()), 2)

    def test_membership_is_explicit_idempotent_and_cascades_with_project(self):
        first = self.add()
        self.assertEqual(self.add().json(), first.json())
        self.assertEqual(len(self.client.get(self.base + '/members', headers=self.headers).json()), 1)
        self.assertEqual(self.client.post(self.base + '/members', headers=self.headers,
                                         json={'email': self.payload['email']}).status_code, 409)
        self.assertEqual(self.client.post(self.base + '/members', headers=self.headers,
                                         json={'email': 'unknown@example.com'}).status_code, 404)
        self.assertEqual(self.client.post(self.base + '/members', headers=self.stranger_headers,
                                         json={'email': 'stranger@example.com'}).status_code, 404)
        self.assertEqual(self.client.delete(f'/projects/{self.project_id}', headers=self.headers).status_code, 204)
        with Session(self.engine) as db:
            self.assertEqual(db.scalars(select(ProjectMember)).all(), [])

    def test_table_setup_creates_only_memberships_and_is_repeatable(self):
        with self.engine.connect() as connection:
            ProjectMember.__table__.drop(connection)
            connection.commit()
            before = set(inspect(connection).get_table_names())
            setup(connection)
            self.assertEqual(set(inspect(connection).get_table_names()), before)
            setup(connection, apply=True)
            setup(connection, apply=True)
            self.assertEqual(set(inspect(connection).get_table_names()), before | {'project_members'})
