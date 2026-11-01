from unittest.mock import patch
from fastapi import HTTPException
from app.services.project_github import GitHubClient
import test_project_content
from test_project_github import COMMIT


class DashboardSyncTests(test_project_content.ProjectContentTests):
    def test_sync_link_unlink_counts_and_aliases(self):
        base = f"/api/projects/{self.project_id}"
        self.client.patch(f"/projects/{self.project_id}", headers=self.headers,
                          json={"github_url": "https://github.com/acme/demo"})
        with patch.object(GitHubClient, "get", return_value=([COMMIT], True)):
            first = self.client.post(base+"/github/sync?branch=main", headers=self.headers)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["created"], 1)
            self.assertTrue(first.json()["has_next"])
            second = self.client.post(base+"/github/sync?branch=other", headers=self.headers)
            self.assertEqual(second.json()["created"], 0)
        activity = self.client.get(base+"/activities?unorganized=true", headers=self.headers).json()[0]
        self.assertNotIn("updated_at", activity)
        for i in range(4):
            story = self.client.post("/stories", headers=self.headers, json={**self.story, "title": str(i)}).json()
        with patch.object(GitHubClient, "get", side_effect=HTTPException(503, "Unavailable")):
            dashboard = self.client.get(base+"/dashboard", headers=self.headers)
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertEqual(dashboard.json()["unorganized_counts"], {"github":1,"figma":0,"notion":0,"total":1})
        self.assertEqual([x["title"] for x in dashboard.json()["recent_stories"]], ["3","2","1"])
        self.assertEqual(len(self.client.get(base+"/stories?limit=3", headers=self.headers).json()),3)
        url = f"/project_activities/{activity['activity_id']}"
        linked = self.client.patch(url, headers=self.headers, json={"story_id": story["id"]})
        self.assertEqual(linked.status_code,200, linked.text)
        self.assertEqual(self.client.get(base+"/activities?unorganized=true", headers=self.headers).json(), [])
        with patch.object(GitHubClient, "get", return_value=([COMMIT], False)):
            self.client.post(base+"/github/sync", headers=self.headers)
        self.assertEqual(self.client.get(url, headers=self.headers).json()["story_id"],story["id"])
        self.client.patch(url, headers=self.headers, json={"story_id":None})
        self.assertEqual(len(self.client.get(base+"/activities?unorganized=true", headers=self.headers).json()),1)
        self.client.patch(url, headers=self.headers, json={"story_id":story["id"]})
        self.client.delete(f"/stories/{story['id']}", headers=self.headers)
        self.assertIsNone(self.client.get(url, headers=self.headers).json()["story_id"])

    def test_cross_project_story_rejected_and_unlinked_dashboard(self):
        other = self.client.post("/projects", headers=self.headers, json=self.project).json()
        story = self.client.post("/stories", headers=self.headers, json={**self.story,"project_id":other["id"]}).json()
        response = self.client.post("/project_activities", headers=self.headers,json={**self.activity,"story_id":story["id"]})
        self.assertEqual(response.status_code,404)
        response = self.client.get(f"/api/projects/{self.project_id}/dashboard",headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["unorganized_counts"]["total"],0)
        self.assertIsNone(response.json()["github"])
        with patch.object(GitHubClient,"get") as get:
            self.assertEqual(self.client.post(f"/api/projects/{self.project_id}/github/sync").status_code,401)
            get.assert_not_called()
