"""프로젝트 저장, 조회, 입력 검사와 회원별 접근 권한을 검증합니다."""

import unittest
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project
import test_signup


class ProjectTests(unittest.TestCase):
    def setUp(self):
        test_signup.SignupTests.setUp(self)
        self.client.post("/api/auth/signup", json=self.payload)
        login = self.client.post("/api/auth/login", json={
            "email": self.payload["email"], "password": self.payload["password"],
        }).json()
        self.owner_id = login["user"]["id"]
        self.headers = {"Authorization": "Bearer " + login["access_token"]}
        self.project = {"project_name": "MOEUM", "description": "프로젝트 변경사항을 기록하고 관리하는 서비스"}

    def tearDown(self):
        test_signup.SignupTests.tearDown(self)

    def test_create_list_and_detail(self):
        response = self.client.post("/projects", json=self.project, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        project = response.json()
        self.assertEqual(project["owner_id"], self.owner_id)
        self.assertEqual(project["project_status"], "active")
        self.assertIsNotNone(project["created_at"])
        self.assertIsNotNone(project["updated_at"])
        self.assertEqual(self.client.get("/projects", headers=self.headers).json(), [project])
        self.assertEqual(self.client.get(f"/projects/{project['id']}", headers=self.headers).json(), project)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Project)).description, self.project["description"])

    def test_cannot_access_or_create_other_members_projects(self):
        project = self.client.post("/projects", json=self.project, headers=self.headers).json()
        other = {**self.payload, "user_id": "other", "email": "other@example.com"}
        self.client.post("/api/auth/signup", json=other)
        token = self.client.post("/api/auth/login", json={
            "email": other["email"], "password": other["password"],
        }).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        self.assertEqual(self.client.get("/projects", headers=headers).json(), [])
        self.assertEqual(self.client.get(f"/projects/{project['id']}", headers=headers).status_code, 404)
        self.assertEqual(self.client.post("/projects", json={
            **self.project, "owner_id": self.owner_id,
        }, headers=headers).status_code, 403)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Project)), 1)

    def test_authentication_required(self):
        self.assertEqual(self.client.post("/projects", json=self.project).status_code, 401)
        self.assertEqual(self.client.get("/projects").status_code, 401)
        self.assertEqual(self.client.get("/projects/1").status_code, 401)

    def test_validation_and_missing_project(self):
        for changes in ({"project_name": "   "}, {"project_name": "x" * 101}, {"owner_id": 0}, {"description": "x" * 10001}):
            self.assertEqual(self.client.post("/projects", json={
                **self.project, **changes,
            }, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get("/projects/99999", headers=self.headers).status_code, 404)
        for url in ("/projects?limit=101", "/projects?offset=-1", "/projects/0"):
            self.assertEqual(self.client.get(url, headers=self.headers).status_code, 422)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Project)), 0)

    def test_optional_description_and_pagination(self):
        for name in ("first", "second"):
            self.assertEqual(self.client.post("/projects", json={
                "owner_id": self.owner_id, "project_name": " " + name + " ",
            }, headers=self.headers).status_code, 201)
        page = self.client.get("/projects?limit=1&offset=1", headers=self.headers).json()
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0]["project_name"], "first")
        self.assertIsNone(page[0]["description"])

    def test_service_urls_are_saved_and_returned_in_all_endpoints(self):
        links = {
            "github_url": "https://github.com/0hyeona/fastapi-practice",
            "figma_url": "https://www.figma.com/design/test/Project",
            "notion_url": "https://www.notion.so/project-page",
        }
        response = self.client.post("/projects", json={**self.project, **links}, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        created = response.json()
        results = [created, self.client.get("/projects", headers=self.headers).json()[0],
                   self.client.get(f"/projects/{created['id']}", headers=self.headers).json()]
        for result in results:
            for field, value in links.items():
                self.assertEqual(result[field], value)
        with Session(self.engine) as db:
            stored = db.get(Project, created["id"])
            for field, value in links.items():
                self.assertEqual(getattr(stored, field), value)

    def test_optional_links_return_null_for_existing_projects(self):
        with Session(self.engine) as db:
            project = Project(owner_id=self.owner_id, project_name="existing")
            db.add(project)
            db.commit()
            project_id = project.id
        created = self.client.post("/projects", json={
            **self.project, "github_url": "  ", "figma_url": None, "notion_url": "",
        }, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        existing = self.client.get(f"/projects/{project_id}", headers=self.headers).json()
        for result in (created.json(), existing):
            for field in ("github_url", "figma_url", "notion_url"):
                self.assertIsNone(result[field])

    def test_invalid_service_urls_create_no_projects(self):
        for field in ("github_url", "figma_url", "notion_url"):
            for value in ("not-a-url", "javascript:alert(1)", "ftp://example.com/file", "https://example.com/" + "x" * 2048):
                with self.subTest(field=field, value=value):
                    response = self.client.post("/projects", json={
                        **self.project, field: value,
                    }, headers=self.headers)
                    self.assertEqual(response.status_code, 422)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Project)), 0)

    def test_archive_restore_preserves_project_and_urls(self):
        original = self.client.post("/projects", json={
            **self.project, "github_url": "https://github.com/0hyeona/fastapi-practice",
        }, headers=self.headers).json()
        project_id = original["id"]
        with Session(self.engine) as db:
            db.get(Project, project_id).updated_at = datetime(2000, 1, 1)
            db.commit()
        response = self.client.patch(f"/projects/{project_id}/archive", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        archived = response.json()
        self.assertEqual(archived["project_status"], "archived")
        self.assertNotEqual(archived["updated_at"], "2000-01-01T00:00:00")
        for field in ("id", "owner_id", "project_name", "description", "github_url", "figma_url", "notion_url", "created_at"):
            self.assertEqual(archived[field], original[field])
        self.assertEqual(self.client.get("/projects", headers=self.headers).json(), [])
        self.assertEqual(self.client.get("/projects?project_status=archived", headers=self.headers).json(), [archived])
        self.assertEqual(self.client.get(f"/projects/{project_id}", headers=self.headers).json(), archived)
        self.assertEqual(self.client.patch(f"/projects/{project_id}/archive", headers=self.headers).json(), archived)
        restored = self.client.patch(f"/projects/{project_id}/restore", headers=self.headers)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["project_status"], "active")
        self.assertEqual(self.client.get("/projects", headers=self.headers).json(), [restored.json()])
        self.assertEqual(self.client.get("/projects?project_status=archived", headers=self.headers).json(), [])
        self.assertEqual(self.client.patch(f"/projects/{project_id}/restore", headers=self.headers).json(), restored.json())
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Project)), 1)

    def test_archive_restore_authentication_and_ownership(self):
        project_id = self.client.post("/projects", json=self.project, headers=self.headers).json()["id"]
        other = {**self.payload, "user_id": "other", "email": "other@example.com"}
        self.client.post("/api/auth/signup", json=other)
        token = self.client.post("/api/auth/login", json={
            "email": other["email"], "password": other["password"],
        }).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        for action in ("archive", "restore"):
            url = f"/projects/{project_id}/{action}"
            self.assertEqual(self.client.patch(url).status_code, 401)
            self.assertEqual(self.client.patch(url, headers=headers).status_code, 404)
            self.assertEqual(self.client.patch(f"/projects/99999/{action}", headers=self.headers).status_code, 404)
            self.assertEqual(self.client.patch(f"/projects/0/{action}", headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get(f"/projects/{project_id}", headers=self.headers).json()["project_status"], "active")

    def test_project_status_filter_before_pagination(self):
        projects = [self.client.post("/projects", json={
            "project_name": name,
        }, headers=self.headers).json() for name in ("first", "second", "third")]
        self.client.patch(f"/projects/{projects[1]['id']}/archive", headers=self.headers)
        page = self.client.get("/projects?limit=1&offset=1", headers=self.headers).json()
        self.assertEqual([p["project_name"] for p in page], ["first"])
        all_projects = self.client.get("/projects?project_status=all", headers=self.headers).json()
        self.assertEqual([p["project_name"] for p in all_projects], ["third", "second", "first"])
        self.assertEqual(self.client.get("/projects?project_status=invalid", headers=self.headers).status_code, 422)

    def test_partial_update_preserves_omitted_fields_and_clears_links(self):
        original = self.client.post("/projects", json={
            **self.project, "github_url": "https://github.com/0hyeona/fastapi-practice",
            "figma_url": "https://www.figma.com/design/test/Project",
        }, headers=self.headers).json()
        url = f"/projects/{original['id']}"
        with Session(self.engine) as db:
            db.get(Project, original["id"]).updated_at = datetime(2000, 1, 1)
            db.commit()
        updated = self.client.patch(url, json={"project_name": "  New name  ", "figma_url": None}, headers=self.headers)
        self.assertEqual(updated.status_code, 200)
        body = updated.json()
        self.assertEqual(body["project_name"], "New name")
        self.assertIsNone(body["figma_url"])
        for field in ("owner_id", "description", "github_url", "created_at", "project_status"):
            self.assertEqual(body[field], original[field])
        self.assertNotEqual(body["updated_at"], "2000-01-01T00:00:00")
        self.assertEqual(self.client.get(url, headers=self.headers).json(), body)
        self.assertEqual(self.client.get("/projects", headers=self.headers).json(), [body])
        self.client.patch(url + "/archive", headers=self.headers)
        response = self.client.patch(url, json={"description": None, "github_url": "", "notion_url": "https://www.notion.so/new-page"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project_status"], "archived")
        self.assertIsNone(response.json()["description"])
        self.assertIsNone(response.json()["github_url"])
        self.assertEqual(response.json()["notion_url"], "https://www.notion.so/new-page")

    def test_invalid_update_changes_nothing(self):
        original = self.client.post("/projects", json=self.project, headers=self.headers).json()
        url = f"/projects/{original['id']}"
        for request in ({}, {"project_name": None}, {"project_name": " "}, {"project_name": "x" * 101},
                        {"owner_id": 999}, {"project_status": "archived"}, {"github_url": "javascript:alert(1)"}):
            self.assertEqual(self.client.patch(url, json=request, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get(url, headers=self.headers).json(), original)

    def test_delete_active_and_archived_projects(self):
        for archived in (False, True):
            project = self.client.post("/projects", json=self.project, headers=self.headers).json()
            url = f"/projects/{project['id']}"
            if archived:
                self.client.patch(url + "/archive", headers=self.headers)
            response = self.client.delete(url, headers=self.headers)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b"")
            self.assertEqual(self.client.get(url, headers=self.headers).status_code, 404)
            self.assertEqual(self.client.delete(url, headers=self.headers).status_code, 404)
            self.assertEqual(self.client.get("/projects?project_status=all", headers=self.headers).json(), [])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Project)), 0)

    def test_update_delete_permissions(self):
        project = self.client.post("/projects", json=self.project, headers=self.headers).json()
        other = {**self.payload, "user_id": "other", "email": "other@example.com"}
        self.client.post("/api/auth/signup", json=other)
        token = self.client.post("/api/auth/login", json={"email": other["email"], "password": other["password"]}).json()["access_token"]
        other_headers = {"Authorization": "Bearer " + token}
        for method, kwargs in ((self.client.patch, {"json": {"project_name": "changed"}}), (self.client.delete, {})):
            url = f"/projects/{project['id']}"
            self.assertEqual(method(url, **kwargs).status_code, 401)
            self.assertEqual(method(url, headers=other_headers, **kwargs).status_code, 404)
            self.assertEqual(method("/projects/99999", headers=self.headers, **kwargs).status_code, 404)
            self.assertEqual(method("/projects/0", headers=self.headers, **kwargs).status_code, 422)
        self.assertEqual(self.client.get(f"/projects/{project['id']}", headers=self.headers).json(), project)
