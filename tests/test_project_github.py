import os
import unittest
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from app.services.project_github import GitHubClient, repository_name
import test_projects

COMMIT = {"sha": "a" * 40, "html_url": "https://github.com/acme/demo/commit/" + "a" * 40,
          "commit": {"message": "Initial commit", "author": {"name": "Tester"},
                     "committer": {"date": "2026-10-28T00:00:00Z"}}, "author": None}
REPO = {"full_name": "acme/demo", "html_url": "https://github.com/acme/demo",
        "default_branch": "main", "language": "Python", "stargazers_count": 1,
        "forks_count": 2, "open_issues_count": 3}


class ProjectGitHubTests(unittest.TestCase):
    def setUp(self):
        test_projects.ProjectTests.setUp(self)
        created = self.client.post("/projects", headers=self.headers, json={
            **self.project, "github_url": "https://github.com/acme/demo"}).json()
        self.base = f"/api/projects/{created['id']}"
        self.project_id = created["id"]

    def tearDown(self):
        test_projects.ProjectTests.tearDown(self)

    def test_four_routes(self):
        with patch.object(GitHubClient, "get", side_effect=[(REPO, False), ([COMMIT], False)]):
            result = self.client.get(self.base + "/dashboard", headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["project"]["id"], self.project_id)
        self.assertEqual(result.json()["github"]["full_name"], "acme/demo")
        with patch.object(GitHubClient, "get", return_value=([COMMIT], True)) as get:
            result = self.client.get(self.base + "/github/commits?branch=feature/test&page=2&per_page=1", headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["has_next"])
        self.assertIsNone(result.json()["items"][0]["author_login"])
        self.assertEqual(get.call_args.args[1], {"sha": "feature/test", "page": 2, "per_page": 1})
        detail = {**COMMIT, "stats": {"additions": 1, "deletions": 0, "total": 1},
                  "files": [{"filename": "a.py", "status": "added", "additions": 1, "deletions": 0, "changes": 1}]}
        with patch.object(GitHubClient, "get", return_value=(detail, True)):
            result = self.client.get(self.base + "/github/commits/" + "a"*40, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()["files"][0]["patch"])
        self.assertTrue(result.json()["has_next"])
        with patch.object(GitHubClient, "get", return_value=([{"name": "main", "commit": {"sha": "a"*40}, "protected": True}], False)):
            result = self.client.get(self.base + "/github/branches", headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["items"][0]["name"], "main")

    def test_auth_and_ownership_before_network(self):
        other = {**self.payload, "user_id": "second", "email": "second@example.com"}
        self.client.post("/api/auth/signup", json=other)
        token = self.client.post("/api/auth/login", json={"email": other["email"], "password": other["password"]}).json()["access_token"]
        with patch.object(GitHubClient, "get") as get:
            for suffix in ("/dashboard", "/github/commits", "/github/commits/" + "a"*40, "/github/branches"):
                self.assertEqual(self.client.get(self.base+suffix).status_code, 401)
                self.assertEqual(self.client.get(self.base+suffix, headers={"Authorization": "Bearer "+token}).status_code, 404)
            get.assert_not_called()

    def test_unlinked_invalid_and_empty(self):
        self.client.patch(f"/projects/{self.project_id}", json={"github_url": None}, headers=self.headers)
        result = self.client.get(self.base+"/dashboard", headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()["github"])
        self.assertEqual(self.client.get(self.base+"/github/commits", headers=self.headers).status_code, 409)
        self.client.patch(f"/projects/{self.project_id}", json={"github_url": "https://example.com/x/y"}, headers=self.headers)
        with patch.object(GitHubClient, "get") as get:
            self.assertEqual(self.client.get(self.base+"/github/branches", headers=self.headers).status_code, 422)
            get.assert_not_called()
        self.client.patch(f"/projects/{self.project_id}", json={"github_url": "https://github.com/acme/demo"}, headers=self.headers)
        with patch.object(GitHubClient, "get", return_value=([], False)):
            self.assertEqual(self.client.get(self.base+"/github/commits", headers=self.headers).json()["items"], [])
        for suffix in ("/github/commits?per_page=101", "/github/branches?page=0", "/github/commits/not-a-sha"):
            self.assertEqual(self.client.get(self.base+suffix, headers=self.headers).status_code, 422)


class GitHubClientTests(unittest.TestCase):
    def test_repository_validation(self):
        self.assertEqual(repository_name("https://github.com/acme/demo.git"), "acme/demo")
        for url in ("https://github.com.evil/a/b", "http://github.com/a/b", "https://github.com/a/b/tree/main",
                    "https://user:pass@github.com/a/b", "https://github.com/a/b?q=x", "https://github.com/a/.."):
            with self.subTest(url=url), self.assertRaises(HTTPException):
                repository_name(url)

    def test_token_is_scoped_to_owner_and_repository(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "secret", "GITHUB_TOKEN_OWNER_ID": "7",
                                     "GITHUB_ALLOWED_REPOSITORIES": "acme/demo"}):
            self.assertIn("Authorization", GitHubClient("acme/demo", 7).headers)
            self.assertNotIn("Authorization", GitHubClient("acme/demo", 8).headers)
            self.assertNotIn("Authorization", GitHubClient("acme/other", 7).headers)

    def test_http_errors_empty_and_pagination(self):
        for code, headers, expected in ((404, {}, 404), (401, {}, 502), (500, {}, 502),
                                        (403, {"x-ratelimit-remaining": "0"}, 503),
                                        (429, {}, 503), (301, {}, 502), (422, {}, 422)):
            with self.subTest(code=code), patch("httpx.Client.get", return_value=httpx.Response(code, headers=headers)):
                with self.assertRaises(HTTPException) as error:
                    GitHubClient("acme/demo", 1).get()
                self.assertEqual(error.exception.status_code, expected)
        with patch("httpx.Client.get", return_value=httpx.Response(409, json={"message": "Git Repository is empty."})):
            self.assertEqual(GitHubClient("acme/demo", 1).get("/commits", empty_list=True), ([], False))
        with patch("httpx.Client.get", return_value=httpx.Response(409, json={"message": "Conflict"})):
            with self.assertRaises(HTTPException):
                GitHubClient("acme/demo", 1).get("/commits", empty_list=True)
        with patch("httpx.Client.get", return_value=httpx.Response(200, json=[], headers={"Link": '<https://api.github.com/repos/acme/demo/commits?page=2>; rel="next"'})):
            self.assertEqual(GitHubClient("acme/demo", 1).get("/commits"), ([], True))

    def test_timeout_network_and_invalid_json(self):
        for exception, expected in ((httpx.ReadTimeout("timeout"), 504), (httpx.ConnectError("offline"), 502)):
            with patch("httpx.Client.get", side_effect=exception):
                with self.assertRaises(HTTPException) as error:
                    GitHubClient("acme/demo", 1).get()
                self.assertEqual(error.exception.status_code, expected)
        with patch("httpx.Client.get", return_value=httpx.Response(200, text="not json")):
            with self.assertRaises(HTTPException) as error:
                GitHubClient("acme/demo", 1).get()
            self.assertEqual(error.exception.status_code, 502)


class DirectRouterTests(unittest.TestCase):
    def test_sqlite_ownership_and_four_response_models(self):
        from datetime import datetime
        from types import SimpleNamespace
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.database.database import Base
        from app.models.user import User
        from app.models.project import Project
        from app.routers import project_github as routes
        from app.schemas.project_github import Dashboard, CommitPage, BranchPage, CommitDetail
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(user_id="tester", name="Tester", email="tester@example.com", password_hash="unused")
            db.add(user)
            db.flush()
            project = Project(owner_id=user.id, project_name="Demo", github_url="https://github.com/acme/demo")
            db.add(project)
            db.commit()
            found = routes.owned_project(project.id, db, user)
            self.assertEqual(found.github_url, "https://github.com/acme/demo")
            with self.assertRaises(HTTPException) as error:
                routes.owned_project(project.id, db, SimpleNamespace(id=user.id+1))
            self.assertEqual(error.exception.status_code, 404)
            with patch.object(GitHubClient, "get", side_effect=[(REPO, False), ([COMMIT], False)]):
                result = Dashboard.model_validate(routes.dashboard(found, db))
            self.assertEqual(result.github.full_name, "acme/demo")
            client = GitHubClient("acme/demo", user.id)
            with patch.object(client, "get", return_value=([COMMIT], True)):
                result = CommitPage.model_validate(routes.commits(2, 1, "feature/test", client))
            self.assertTrue(result.has_next)
            with patch.object(client, "get", return_value=([{"name":"main", "commit":{"sha":"a"*40}, "protected":False}], False)):
                result = BranchPage.model_validate(routes.branches(1, 30, client))
            self.assertEqual(result.items[0].name, "main")
            detail = {**COMMIT, "stats":{"additions":1,"deletions":0,"total":1}, "files":[]}
            with patch.object(client, "get", return_value=(detail, False)):
                result = CommitDetail.model_validate(routes.commit_detail("a"*40, 1, 100, client))
            self.assertEqual(result.stats.total, 1)
        engine.dispose()
