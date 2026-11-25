import unittest
from json import dumps, loads
from unittest.mock import patch

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_projects
from app.models.story import Story
from app.models.project_activity import ProjectActivity


class ProjectContentTests(unittest.TestCase):
    def setUp(self):
        test_projects.ProjectTests.setUp(self)
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        self.project_id = self.client.post("/projects", json=self.project, headers=self.headers).json()["id"]
        self.story = {"project_id": self.project_id, "title": "Story", "content": "Body"}
        self.activity = {"project_id": self.project_id, "source": "github", "activity_type": "push", "title": "Commit", "occurred_at": "2026-10-28T15:00:00+09:00"}

    def tearDown(self):
        test_projects.ProjectTests.tearDown(self)

    def test_crud_and_project_cascade(self):
        for path, payload, model in (("/stories", self.story, Story), ("/project_activities", self.activity, ProjectActivity)):
            created = self.client.post(path, json=payload, headers=self.headers)
            self.assertEqual(created.status_code, 201, created.text)
            body = created.json()
            if model is ProjectActivity:
                self.assertIn("activity_id", body)
                self.assertNotIn("id", body)
                self.assertEqual(body["occurred_at"], "2026-10-28T06:00:00")
            else:
                self.assertEqual(body["story_status"], "draft")
            id_field = "activity_id" if path == "/project_activities" else "id"
            url = f"{path}/{body[id_field]}"
            self.assertEqual(self.client.get(url, headers=self.headers).json(), body)
            self.assertEqual(self.client.get(path, headers=self.headers).json(), [body])
            patched = self.client.patch(url, json={"title": "Updated"}, headers=self.headers)
            self.assertEqual(patched.status_code, 200)
            self.assertEqual(patched.json()["title"], "Updated")
            self.assertEqual(self.client.delete(url, headers=self.headers).status_code, 204)
            self.assertEqual(self.client.get(url, headers=self.headers).status_code, 404)
            self.client.post(path, json=payload, headers=self.headers)
        self.assertEqual(self.client.delete(f"/projects/{self.project_id}", headers=self.headers).status_code, 204)
        with Session(self.engine) as db:
            self.assertEqual(db.scalars(select(Story)).all(), [])
            self.assertEqual(db.scalars(select(ProjectActivity)).all(), [])

    def test_permissions_on_every_operation(self):
        other = {**self.payload, "user_id": "other", "email": "other@example.com"}
        self.client.post("/api/auth/signup", json=other)
        token = self.client.post("/api/auth/login", json={"email": other["email"], "password": other["password"]}).json()["access_token"]
        other_headers = {"Authorization": "Bearer " + token}
        with patch("httpx.post") as provider:
            denied = self.client.post("/stories/analyze", headers=other_headers,
                                      json={"project_id": self.project_id, "activity_ids": [1]})
            self.assertEqual(denied.status_code, 404)
            provider.assert_not_called()
        for path, payload in (("/stories", self.story), ("/project_activities", self.activity)):
            body = self.client.post(path, json=payload, headers=self.headers).json()
            id_field = "activity_id" if path == "/project_activities" else "id"
            url = f"{path}/{body[id_field]}"
            if path == "/stories":
                self.assertEqual(self.client.get(f"{url}/export", headers=other_headers).status_code, 404)
            for headers, status in (({}, 401), (other_headers, 404)):
                self.assertEqual(self.client.post(path, json=payload, headers=headers).status_code, status)
                self.assertEqual(self.client.get(url, headers=headers).status_code, status)
                self.assertEqual(self.client.patch(url, json={"title": "Stolen"}, headers=headers).status_code, status)
                self.assertEqual(self.client.delete(url, headers=headers).status_code, status)
                self.assertEqual(self.client.get(f"{path}?project_id={self.project_id}", headers=headers).status_code, status)
            self.assertEqual(self.client.get(path, headers=other_headers).json(), [])
            self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(self.client.post(path, json={**payload, "project_id": 9999}, headers=self.headers).status_code, 404)

    def test_story_defaults(self):
        response = self.client.post("/stories", json={"project_id": self.project_id, "title": "Draft"}, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["content"], "")
        self.assertEqual(response.json()["story_status"], "draft")
        for field in ("why", "problem", "solution", "result", "learned", "next_steps", "ai_analysis"):
            self.assertIsNone(response.json()[field])

    def test_story_details_persist_and_round_trip(self):
        details = {
            "why": "작업 배경\n두 번째 줄", "problem": "조회 누락", "solution": "API 연결",
            "result": "저장 완료", "learned": "필드 매핑", "next_steps": "화면 연결",
            "ai_analysis": {"summary": "분석 결과", "items": ["개선", {"score": 0.9}], "done": True},
        }
        response = self.client.post("/stories", json={**self.story, **details}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        url = f"/stories/{body['id']}"
        with Session(self.engine) as db:
            stored = db.get(Story, body["id"])
            for field, value in details.items():
                self.assertEqual(getattr(stored, field), value)
            self.assertEqual(Story.story_status.property.columns[0].name, "status")
        for result in (body, self.client.get(url, headers=self.headers).json(),
                       self.client.get(f"/stories?project_id={self.project_id}", headers=self.headers).json()[0]):
            for field, value in details.items():
                self.assertEqual(result[field], value)
        changes = {"problem": "수정한 문제", "ai_analysis": {"summary": "재분석"}, "story_status": "published"}
        updated = self.client.patch(url, json=changes, headers=self.headers)
        self.assertEqual(updated.status_code, 200, updated.text)
        for field, value in {**details, **changes}.items():
            self.assertEqual(updated.json()[field], value)
        cleared = self.client.patch(url, json={"why": None, "ai_analysis": None}, headers=self.headers)
        self.assertEqual(cleared.status_code, 200, cleared.text)
        fetched = self.client.get(url, headers=self.headers).json()
        self.assertIsNone(fetched["why"])
        self.assertIsNone(fetched["ai_analysis"])
        self.assertEqual(fetched["problem"], changes["problem"])
        self.assertEqual(fetched["content"], self.story["content"])

    def test_story_details_validation(self):
        for changes in ({"why": {"text": "invalid"}}, {"next_steps": "x" * 15001}):
            response = self.client.post("/stories", json={**self.story, **changes}, headers=self.headers)
            self.assertEqual(response.status_code, 422)
        body = self.client.post("/stories", json=self.story, headers=self.headers).json()
        for changes in ({"content": None}, {"story_status": None}, {"solution": []}):
            response = self.client.patch(f"/stories/{body['id']}", json=changes, headers=self.headers)
            self.assertEqual(response.status_code, 422)

    def test_story_analysis_save_and_export(self):
        notion_url = 'https://www.notion.so/' + 'a' * 32
        with Session(self.engine) as db:
            from app.models.project import Project
            db.get(Project, self.project_id).notion_url = notion_url
            db.commit()
        ids = []
        for source in ('github', 'figma', 'notion'):
            row = self.client.post('/project_activities', headers=self.headers,
                                   json={**self.activity, 'source': source, 'description': source + ' evidence',
                                         'source_url': notion_url if source == 'notion' else None}).json()
            ids.append(row['activity_id'])
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch('httpx.post') as provider:
            response = self.client.post('/stories/analyze', headers=self.headers,
                                        json={'project_id': self.project_id, 'activity_ids': ids, 'mode': 'code'})
            self.assertEqual(response.status_code, 200, response.text)
            analysis = response.json()
            self.assertEqual(analysis['tags'], ['github', 'figma', 'notion'])
            self.assertIn('notion evidence', analysis['summary'])
            self.assertIsNone(analysis['before'])
            provider.assert_not_called()
        created = self.client.post('/stories', headers=self.headers, json={
            **self.story, 'title': analysis['title'], 'ai_analysis': analysis, 'activity_ids': ids})
        self.assertEqual(created.status_code, 201, created.text)
        story_id = created.json()['id']
        detail = self.client.get(f'/stories/{story_id}', headers=self.headers).json()
        self.assertEqual(detail['ai_analysis'], analysis)
        published = self.client.patch(f'/stories/{story_id}', headers=self.headers, json={'story_status': 'published'})
        self.assertEqual(published.json()['story_status'], 'published')
        linked = self.client.get(f'/api/projects/{self.project_id}/activities?story_id={story_id}', headers=self.headers)
        self.assertCountEqual([row['activity_id'] for row in linked.json()], ids)
        exported = self.client.get(f'/stories/{story_id}/export', headers=self.headers)
        self.assertEqual(exported.status_code, 200)
        self.assertIn('notion evidence', exported.text)
        self.assertEqual(self.client.get(f'/stories/{story_id}/export').status_code, 401)

    def test_story_bulk_link_rejects_invalid_selection_without_saving(self):
        activity = self.client.post("/project_activities", json=self.activity, headers=self.headers).json()
        activity_id = activity["activity_id"]
        request = {**self.story, "activity_ids": [activity_id, 9999]}
        self.assertEqual(self.client.post("/stories", headers=self.headers, json=request).status_code, 404)
        second = self.client.post("/projects", json=self.project, headers=self.headers).json()["id"]
        self.assertEqual(self.client.post("/stories", headers=self.headers,
                                         json={**request, "project_id": second, "activity_ids": [activity_id]}).status_code, 404)
        self.assertEqual(self.client.get("/stories", headers=self.headers).json(), [])
        self.assertIsNone(self.client.get(f"/project_activities/{activity_id}", headers=self.headers).json()["story_id"])

        request["activity_ids"] = [activity_id, activity_id]
        created = self.client.post("/stories", headers=self.headers, json=request)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/stories", headers=self.headers, json=request).status_code, 409)
        self.assertEqual(len(self.client.get("/stories", headers=self.headers).json()), 1)

    def test_story_analysis_access_and_selection_validation(self):
        activity = self.client.post('/project_activities', json=self.activity, headers=self.headers).json()
        request = {'project_id': self.project_id, 'activity_ids': [activity['activity_id']]}
        path = '/stories/analyze'
        self.assertEqual(self.client.post(path, json=request).status_code, 401)
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch('httpx.post') as provider:
            for changes, status in (({'activity_ids': []}, 422), ({'activity_ids': [9999]}, 404),
                                    ({'activity_ids': [activity['activity_id']] * 21}, 422), ({'mode': 'invalid'}, 422)):
                self.assertEqual(self.client.post(path, headers=self.headers, json={**request, **changes}).status_code, status)
            self.assertEqual(self.client.post(path, headers=self.headers, json=request).status_code, 200)
            section = self.client.post(path, headers=self.headers, json={**request, 'section': 'before'})
            self.assertEqual(section.json(), {'before': None})
            provider.assert_not_called()

    def test_validation_and_partial_update(self):
        for path, payload in (("/stories", self.story), ("/project_activities", self.activity)):
            body = self.client.post(path, json=payload, headers=self.headers).json()
            id_field = "activity_id" if path == "/project_activities" else "id"
            url = f"{path}/{body[id_field]}"
            for invalid in ({}, {"title": None}, {"title": " "}, {"project_id": 2}, {"title": "x" * 201}):
                self.assertEqual(self.client.patch(url, json=invalid, headers=self.headers).status_code, 422)
            for query in ("limit=101", "offset=-1", "project_id=0"):
                self.assertEqual(self.client.get(path + "?" + query, headers=self.headers).status_code, 422)
            self.assertEqual(self.client.get(url, headers=self.headers).json(), body)
        for invalid in ({"source": "slack"}, {"occurred_at": "2026-10-28T10:00:00"}, {"source_url": "javascript:alert(1)"}):
            self.assertEqual(self.client.post("/project_activities", json={**self.activity, **invalid}, headers=self.headers).status_code, 422)
        activity = self.client.post("/project_activities", json={**self.activity, "source_url": "https://github.com/example/repo", "description": "Text"}, headers=self.headers).json()
        result = self.client.patch(f"/project_activities/{activity['activity_id']}", json={"source_url": None, "description": None}, headers=self.headers).json()
        self.assertIsNone(result["source_url"])
        self.assertIsNone(result["description"])
        self.assertEqual(result["source"], "github")

    def test_filters_pagination_and_time_order(self):
        second_project = self.client.post("/projects", json=self.project, headers=self.headers).json()["id"]
        for index, source in enumerate(("github", "notion", "github")):
            self.client.post("/project_activities", json={**self.activity, "source": source, "title": str(index), "occurred_at": f"2026-10-{28-index}T06:00:00Z"}, headers=self.headers)
            self.client.post("/stories", json={**self.story, "title": str(index), "story_status": "published" if index != 1 else "draft"}, headers=self.headers)
        self.client.post("/stories", json={**self.story, "project_id": second_project}, headers=self.headers)
        stories = self.client.get(f"/stories?project_id={self.project_id}&story_status=published&limit=1&offset=1", headers=self.headers).json()
        self.assertEqual([r["title"] for r in stories], ["0"])
        activities = self.client.get("/project_activities?source=github&limit=1&offset=1", headers=self.headers).json()
        self.assertEqual([r["title"] for r in activities], ["2"])
        for path in ("/stories?story_status=invalid", "/project_activities?source=invalid"):
            self.assertEqual(self.client.get(path, headers=self.headers).status_code, 422)
