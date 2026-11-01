"""Read GitHub data without storing commits or branches in MySQL."""
import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException


def repository_name(url):
    if not url:
        raise HTTPException(409, "프로젝트에 GitHub 저장소 URL을 먼저 등록해주세요.")
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname == "github.com"
                 and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "https://github.com/소유자/저장소 형식으로 등록해주세요.")
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", path) or path.split("/")[1] in (".", ".."):
        raise HTTPException(422, "GitHub 저장소 루트 URL을 등록해주세요.")
    return path


class GitHubClient:
    def __init__(self, repository, owner_id):
        self.repository = repository
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        # A shared token must not grant all app users access to private repositories.
        allowed = {s.strip().lower() for s in os.getenv("GITHUB_ALLOWED_REPOSITORIES", "").split(",")}
        if str(owner_id) == os.getenv("GITHUB_TOKEN_OWNER_ID", "").strip() and repository.lower() in allowed:
            token = os.getenv("GITHUB_TOKEN", "").strip()
            if token:
                self.headers["Authorization"] = f"Bearer {token}"

    def get(self, path="", params=None, empty_list=False):
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                response = client.get(f"https://api.github.com/repos/{self.repository}{path}",
                                      headers=self.headers, params=params)
        except httpx.TimeoutException as exc:
            raise HTTPException(504, "GitHub 응답 시간이 초과되었습니다.") from exc
        except httpx.RequestError as exc:
            raise HTTPException(502, "GitHub에 연결할 수 없습니다.") from exc
        if response.status_code == 409 and empty_list:
            try:
                is_empty = "empty" in response.json().get("message", "").lower()
            except (ValueError, AttributeError):
                is_empty = False
            if is_empty:
                return [], False
        if response.status_code in (403, 429):
            limited = (response.status_code == 429 or response.headers.get("x-ratelimit-remaining") == "0"
                       or "retry-after" in response.headers)
            raise HTTPException(503 if limited else 502,
                                "GitHub 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요." if limited
                                else "GitHub 저장소 접근 권한을 확인해주세요.")
        if response.status_code == 404:
            raise HTTPException(404, "GitHub 저장소 또는 브랜치/커밋을 찾을 수 없습니다.")
        if response.status_code == 401:
            raise HTTPException(502, "서버의 GitHub 토큰 설정을 확인해주세요.")
        if response.status_code == 422:
            raise HTTPException(422, "GitHub 조회 조건을 확인해주세요.")
        if response.status_code != 200:
            raise HTTPException(502, "GitHub 조회에 실패했습니다. 저장소 주소를 확인해주세요.")
        try:
            return response.json(), "next" in response.links
        except ValueError as exc:
            raise HTTPException(502, "GitHub 응답을 읽을 수 없습니다.") from exc


def commit_summary(item):
    author = item["commit"].get("author") or {}
    account = item.get("author") or {}
    return {
        "sha": item["sha"], "message": item["commit"]["message"],
        "author_name": author.get("name"), "author_login": account.get("login"),
        "avatar_url": account.get("avatar_url"),
        "committed_at": (item["commit"].get("committer") or {}).get("date"),
        "html_url": item["html_url"],
    }
