"""Rule-based Story drafts from selected records and GitHub diff evidence."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Lock
from time import monotonic
import re

from fastapi import HTTPException
from app.schemas.story import StoryAnalysis
from app.services.project_content_service import require_project, selected_activities
from app.services.project_github import GitHubClient, repository_name

_cache = {}
_cache_lock = Lock()


def _clip(value, limit=3000):
    value = str(value or "").strip()
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _commit(client, sha):
    authorization = sha256(client.headers.get("Authorization", "").encode()).hexdigest()
    key = (client.repository.lower(), authorization, sha)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
    data, has_next = client.get(f"/commits/{sha}", {"per_page": 100})
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise HTTPException(502, "GitHub 변경 파일 응답을 확인할 수 없어요.")
    files = []
    for row in data["files"][:100]:
        if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
            raise HTTPException(502, "GitHub 변경 파일 형식을 확인할 수 없어요.")
        if any(not isinstance(row.get(field, 0), int) or row.get(field, 0) < 0
               for field in ("additions", "deletions")):
            raise HTTPException(502, "GitHub 변경 줄 수를 확인할 수 없어요.")
        patch = row.get("patch")
        patch = patch if isinstance(patch, str) else ""
        lines = patch.splitlines()
        files.append({
            "name": _clip(row["filename"], 240),
            "previous": _clip(row.get("previous_filename"), 240),
            "status": str(row.get("status", "modified")),
            "added": row.get("additions", 0), "deleted": row.get("deletions", 0),
            "before": [line[1:] for line in lines if line.startswith("-")],
            "after": [line[1:] for line in lines if line.startswith("+")],
            "has_patch": bool(patch),
        })
    result = {"files": files, "partial": has_next}
    with _cache_lock:
        now = monotonic()
        for old in [key for key, item in _cache.items() if item[0] <= now]:
            del _cache[old]
        if len(_cache) >= 128:
            del _cache[next(iter(_cache))]
        _cache[key] = (now + 300, result)
    return result


def _sha(activity, repository):
    external_id = activity["external_id"] or ""
    if ":" in external_id:
        recorded_repository, external_id = external_id.rsplit(":", 1)
        if recorded_repository.lower() != repository.lower():
            return None
    return external_id if re.fullmatch(r"[a-fA-F0-9]{40}", external_id) else None


def analyze(db, request, owner_id):
    project = require_project(db, request.project_id, owner_id)
    rows = selected_activities(db, request.project_id, request.activity_ids)
    activities = [{key: getattr(row, key, None) for key in
                   ("source", "title", "description", "external_id", "branch_name")}
                  for row in rows]
    github_url, project_owner = project.github_url, project.owner_id
    client, repository, setup_warning = None, "", ""
    if any(row["source"] == "github" for row in activities):
        try:
            repository = repository_name(github_url)
            client = GitHubClient(repository, project_owner, db=db)
        except HTTPException as error:
            setup_warning = str(error.detail)
    # Copy ORM evidence and credentials before releasing the read transaction.
    db.rollback()
    shas = list(dict.fromkeys(filter(None, (_sha(row, repository) for row in activities
                                          if row["source"] == "github")))) if client else []

    def fetch(sha):
        try:
            return sha, _commit(client, sha), None
        except HTTPException as error:
            return sha, None, str(error.detail)

    with ThreadPoolExecutor(max_workers=4) as pool:
        details = {sha: (data, warning) for sha, data, warning in pool.map(fetch, shas)}
    mode = getattr(request, "mode", "semantic")
    summary, before, after, tags = [], [], [], []
    for row in activities:
        source = str(row["source"] or "unknown")
        if source not in tags:
            tags.append(source)
        title = _clip(row["title"] or "제목 없는 변경사항", 200)
        summary.append(f"[{source}] {title}")
        description = _clip(row["description"], 800 if mode == "code" else 400)
        if description and description != title:
            summary.append(description)
        if source != "github":
            continue
        sha = _sha(row, repository)
        data, warning = details.get(sha, (None, setup_warning or "현재 저장소의 커밋 ID를 확인할 수 없어요."))
        if not data:
            summary.append(f"코드 상세 수집 미완료: {warning} 저장된 제목·설명만 정리했어요.")
            continue
        files = data["files"]
        summary.append(f"확인한 변경 파일 {len(files)}개 · 추가 {sum(f['added'] for f in files)}줄 · 삭제 {sum(f['deleted'] for f in files)}줄")
        if mode in ("balanced", "code"):
            summary.extend(f"{f['name']} ({f['status']}, +{f['added']}/-{f['deleted']})"
                           + (f" · 이전 이름: {f['previous']}" if f["previous"] else "") for f in files[:20])
        if data["partial"]:
            summary.append("변경 파일이 많아 첫 100개만 확인했어요. 위 줄 수는 확인한 파일 기준이에요.")
        missing_patches = sum(not f["has_patch"] for f in files)
        if missing_patches:
            summary.append(f"파일 {missing_patches}개는 GitHub가 diff를 제공하지 않아 코드 내용을 비교하지 못했어요.")
        for field, output in (("before", before), ("after", after)):
            for file in files:
                if file[field]:
                    count = 12 if mode == "code" else 3
                    output.append(f"{sha[:7]} · {file['name']}\n" + "\n".join(_clip(line, 180) for line in file[field][:count]))
    summary.append("저장된 작업 기록과 확인 가능한 diff를 정리한 자체 분석이에요. 변경 의도·성과는 작성자가 확인해주세요.")
    first_title = str(activities[0]["title"] or "프로젝트 변경사항").splitlines()[0]
    suffix = f" 외 {len(activities) - 1}건" if len(activities) > 1 else ""
    result = {
        "title": _clip(first_title, 200 - len(suffix)) + suffix,
        "tags": tags[:10], "summary": _clip("\n".join(summary)),
        "before": _clip("삭제·교체된 코드 일부\n" + "\n\n".join(before)) if before else None,
        "after": _clip("추가·교체된 코드 일부\n" + "\n\n".join(after)) if after else None,
    }
    if request.section:
        result = {request.section: result[request.section]}
    return StoryAnalysis.model_validate(result)
