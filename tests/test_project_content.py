import unittest
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
        for path, payload in (("/stories", self.story), ("/project_activities", self.activity)):
            body = self.client.post(path, json=payload, headers=self.headers).json()
            id_field = "activity_id" if path == "/project_activities" else "id"
            url = f"{path}/{body[id_field]}"
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
