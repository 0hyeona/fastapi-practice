"""Scoped Figma/Notion collection into the existing activities table."""
import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.services.sync_history import record_sync


def resource_id(source, url):
    if not url:
        raise HTTPException(409, f"{source} URL을 프로젝트에 먼저 등록하세요.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        if source == 'figma':
            if host not in ('figma.com', 'www.figma.com'):
                raise ValueError()
            match = re.fullmatch(r'/(?:design|file|board|slides|proto|make)/([A-Za-z0-9]+)(?:/[^/]*)?/?', parsed.path)
            if not match:
                raise ValueError()
            return match[1]
        if source != 'notion' or not (host in ('notion.so', 'www.notion.so', 'notion.site', 'notion.com', 'www.notion.com', 'app.notion.com') or host.endswith('.notion.site')):
            raise ValueError()
        match = re.search(r'([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})/?$', parsed.path)
        if not match:
            raise ValueError()
        return UUID(match[1]).hex
    except (ValueError, TypeError):
        raise HTTPException(422, f"올바른 {source} 파일/페이지 링크를 입력하세요.") from None


def scoped_token(source, owner_id, resource):
    prefix = source.upper()
    token = os.getenv(f'{prefix}_TOKEN', '').strip()
    configured_owner = os.getenv(f'{prefix}_TOKEN_OWNER_ID', '').strip()
    allow_name = 'FIGMA_ALLOWED_FILE_KEYS' if source == 'figma' else 'NOTION_ALLOWED_PAGE_IDS'
    allowed = {part.strip() for part in os.getenv(allow_name, '').split(',') if part.strip()}
    if source == 'notion':
        allowed = {part.replace('-', '').lower() for part in allowed}
    if not token or not configured_owner or not allowed:
        raise HTTPException(503, f'{prefix}_TOKEN, {prefix}_TOKEN_OWNER_ID, {allow_name} 설정이 필요합니다.')
    if str(owner_id) != configured_owner or resource not in allowed:
        raise HTTPException(403, f'{source} 연결이 이 사용자와 파일/페이지에 허용되지 않았습니다.')
    return token


def connection_state(project, source):
    url = getattr(project, source + '_url')
    if not url:
        return {'linked': False, 'configured': False, 'resource_id': None, 'detail': '프로젝트 링크가 없습니다.'}
    try:
        resource = resource_id(source, url)
        scoped_token(source, project.owner_id, resource)
    except HTTPException as error:
        return {'linked': True, 'configured': False, 'resource_id': None, 'detail': error.detail}
    return {'linked': True, 'configured': True, 'resource_id': resource,
            'detail': '서버 설정 확인 완료. 실제 접근 권한은 동기화 실행 시 확인합니다.'}


def fetch_json(source, url, headers, params=None):
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(url, headers=headers, params=params)
    except httpx.TimeoutException:
        raise HTTPException(504, f'{source} 응답 시간이 초과되었습니다.') from None
    except httpx.RequestError:
        raise HTTPException(502, f'{source} 서버에 연결할 수 없습니다.') from None
    if response.status_code == 429:
        retry = response.headers.get('retry-after', '')
        headers = {'Retry-After': retry} if retry.isdigit() else None
        raise HTTPException(503, f'{source} 요청 한도 초과. 잠시 후 재시도하세요.', headers=headers)
    if response.status_code in (401, 403):
        raise HTTPException(502, f'{source} 토큰·읽기 권한·페이지 공유 설정을 확인하세요.')
    if response.status_code == 404:
        raise HTTPException(404, f'{source} 파일/페이지를 찾을 수 없거나 접근 권한이 없습니다.')
    if response.status_code != 200:
        raise HTTPException(502, f'{source} 조회에 실패했습니다.')
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except ValueError:
        raise HTTPException(502, f'{source} 응답 형식이 올바르지 않습니다.') from None


def occurred_at(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Missing timezone')
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def event(resource, revision, title, description, url, timestamp, kind):
    return dict(external_id=hashlib.sha256(f'{resource}:{revision}'.encode()).hexdigest(),
                title=(title or '변경사항')[:200], description=description,
                source_url=url, occurred_at=occurred_at(timestamp), activity_type=kind)


def figma_cursor(value, resource):
    """Only permit same-file pagination on the fixed Figma API origin."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise HTTPException(422, "올바른 Figma next_cursor를 입력하세요.") from None
    if (parsed.scheme != 'https' or parsed.netloc != 'api.figma.com'
            or parsed.path != f'/v1/files/{resource}/versions' or parsed.fragment):
        raise HTTPException(422, '이 Figma 파일의 next_cursor만 사용할 수 있습니다.')
    return value


def collect_figma(project, cursor=None):
    resource = resource_id('figma', project.figma_url)
    token = scoped_token('figma', project.owner_id, resource)
    headers = {'X-Figma-Token': token}
    endpoint = f'https://api.figma.com/v1/files/{resource}'
    target = figma_cursor(cursor, resource) if cursor else endpoint + '/versions'
    versions = fetch_json('figma', target, headers)
    try:
        next_cursor = (versions.get('pagination') or {}).get('next_page') or None
        if next_cursor:
            figma_cursor(next_cursor, resource)
        rows = []
        for version in versions['versions']:
            rows.append(event(resource, version['id'], version.get('label') or 'Figma 버전 변경',
                version.get('description') or '', f'https://www.figma.com/file/{resource}?version-id={version["id"]}',
                version['created_at'], 'file_version'))
        # Capture the current file state as well as named/saved history on the first page.
        if not cursor:
            current = fetch_json('figma', endpoint, headers, {'depth': 1})
            rows.append(event(resource, current['version'], current.get('name') or 'Figma 파일 변경',
                '수집 시점의 파일 버전', f'https://www.figma.com/file/{resource}', current['lastModified'], 'file_version'))
        rows = list({row['external_id']: row for row in reversed(rows)}.values())
        return rows, next_cursor
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(502, 'Figma 변경사항 응답 형식이 올바르지 않습니다.') from None


def collect_notion(project):
    resource = resource_id('notion', project.notion_url)
    token = scoped_token('notion', project.owner_id, resource)
    data = fetch_json('notion', f'https://api.notion.com/v1/pages/{resource}',
                      {'Authorization': f'Bearer {token}', 'Notion-Version': '2026-03-11'})
    try:
        if data['object'] != 'page' or UUID(data['id']).hex != resource:
            raise ValueError()
        title = next((prop['title'] for prop in data['properties'].values() if prop.get('type') == 'title'), [])
        name = ''.join(part.get('plain_text', part.get('text', {}).get('content', '')) for part in title)
        timestamp = data['last_edited_time']
        # This is an observed page revision, not an assertion of full edit history.
        row = event(resource, occurred_at(timestamp).isoformat(), name or 'Notion 페이지 변경',
                    '수집 시점에 확인한 페이지 최근 수정 상태', f'https://www.notion.so/{resource}',
                    timestamp, 'page_updated')
        return [row], None
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(502, 'Notion 페이지 응답 형식이 올바르지 않습니다.') from None


def _sync_external(db, project, source, cursor, progress):
    if source not in ('figma', 'notion'):
        raise HTTPException(422, '지원하지 않는 서비스입니다.')
    if source == 'notion' and cursor:
        raise HTTPException(422, 'Notion 페이지 동기화에는 cursor가 없습니다.')
    original_url = getattr(project, source + '_url')
    original_owner = project.owner_id
    rows, next_cursor = collect_figma(project, cursor) if source == 'figma' else collect_notion(project)
    progress["fetched"] = len(rows)
    locked = db.scalar(select(Project).where(Project.id == project.id).with_for_update().execution_options(populate_existing=True))
    if locked is None or locked.owner_id != original_owner or getattr(locked, source + '_url') != original_url:
        raise HTTPException(409, '프로젝트 연결이 변경되었습니다. 다시 동기화하세요.')
    ids = [row['external_id'] for row in rows]
    existing = set(db.scalars(select(ProjectActivity.external_id).where(
        ProjectActivity.project_id == project.id, ProjectActivity.source == source,
        ProjectActivity.external_id.in_(ids)).with_for_update()).all())
    created = 0
    for row in rows:
        if row['external_id'] not in existing:
            db.add(ProjectActivity(project_id=project.id, source=source, **row))
            existing.add(row['external_id'])
            created += 1
    return {'source': source, 'fetched': len(rows), 'created': created, 'existing': len(rows)-created,
            'has_next': bool(next_cursor), 'next_cursor': next_cursor}



def sync_external(db, project, source, cursor=None):
    if source not in ("figma", "notion"):
        raise HTTPException(422, "Unsupported source.")
    return record_sync(db, project, source, lambda progress: _sync_external(db, project, source, cursor, progress))
