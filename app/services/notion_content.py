"""Collect complete text snapshots and compare stable block IDs."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.project_notion_snapshot import ProjectNotionSnapshot


def rich_text(parts):
    if not isinstance(parts, list):
        raise ValueError("Invalid rich text")
    return ''.join(part['plain_text'] if 'plain_text' in part else part['text']['content'] for part in parts)


def collect(project, api):
    resource = api.resource_id('notion', project.notion_url)
    token = api.scoped_token('notion', project.owner_id, resource)
    headers = {'Authorization': f'Bearer {token}', 'Notion-Version': '2026-03-11'}
    endpoint = f'https://api.notion.com/v1/pages/{resource}'
    blocks = {}
    requests = 0

    def page_title(data):
        if data['object'] != 'page' or UUID(data['id']).hex != resource:
            raise ValueError('Invalid page')
        title = next(prop['title'] for prop in data['properties'].values() if prop.get('type') == 'title')
        api.occurred_at(data['last_edited_time'])
        return rich_text(title)

    def children(parent, depth=0):
        nonlocal requests
        if depth > 50:
            raise HTTPException(502, 'Notion nesting limit exceeded; snapshot preserved.')
        cursor = None
        seen = set()
        while True:
            requests += 1
            if requests > 200:
                raise HTTPException(502, 'Notion collection limit exceeded; snapshot preserved.')
            params = {'page_size': 100}
            if cursor:
                params['start_cursor'] = cursor
            data = api.fetch_json('notion', f'https://api.notion.com/v1/blocks/{parent}/children', headers, params)
            if data['object'] != 'list' or not isinstance(data['results'], list) or type(data['has_more']) is not bool:
                raise ValueError('Invalid block list')
            for block in data['results']:
                block_id = UUID(block['id']).hex
                kind = block['type']
                if block['object'] != 'block' or block_id in blocks or type(block['has_children']) is not bool:
                    raise ValueError('Invalid block')
                payload = block[kind]
                if not isinstance(payload, dict):
                    raise ValueError('Invalid block payload')
                text = rich_text(payload.get('rich_text', payload.get('caption', [])))
                if kind == 'table_row':
                    text = ' | '.join(rich_text(cell) for cell in payload['cells'])
                if kind in ('child_page', 'child_database'):
                    text = payload['title']
                if kind == 'to_do':
                    if type(payload['checked']) is not bool:
                        raise ValueError('Invalid checkbox')
                    text = ('[x] ' if payload['checked'] else '[ ] ') + text
                blocks[block_id] = {'type': kind, 'text': text}
                # Separate pages/databases are outside this page's text scope.
                if block['has_children'] and kind not in ('child_page', 'child_database'):
                    children(block_id, depth + 1)
            if not data['has_more']:
                break
            cursor = data['next_cursor']
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise ValueError('Invalid pagination')
            seen.add(cursor)

    try:
        page = api.fetch_json('notion', endpoint, headers)
        title = page_title(page)
        children(resource)
        final = api.fetch_json('notion', endpoint, headers)
        if page_title(final) != title or final['last_edited_time'] != page['last_edited_time']:
            raise HTTPException(409, 'Notion page changed during collection; retry.')
        return resource, {'title': title, 'blocks': blocks}, page['last_edited_time']
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration):
        raise HTTPException(502, 'Invalid Notion content response; snapshot preserved.') from None


def changes(before, after):
    if before['title'] != after['title']:
        yield 'title_changed', '제목 변경', before['title'], after['title']
    old, new = before['blocks'], after['blocks']
    for key, block in new.items():
        if key not in old:
            yield 'content_added', '내용 추가', None, block['text']
        elif old[key] != block:
            yield 'content_updated', '내용 수정', old[key]['text'], block['text']
    for key, block in old.items():
        if key not in new:
            yield 'content_deleted', '내용 삭제', block['text'], None


def sync(db, project, progress, api):
    original_url, original_owner = project.notion_url, project.owner_id
    # Serialize collectors before reading remote data so an older fetch cannot
    # overwrite a newer snapshot. record_sync owns commit/rollback of this lock.
    locked = db.scalar(select(Project).where(Project.id == project.id).with_for_update().execution_options(populate_existing=True))
    if locked is None or locked.owner_id != original_owner or locked.notion_url != original_url:
        raise HTTPException(409, 'Project connection changed; retry.')
    resource, current, timestamp = collect(locked, api)
    progress['fetched'] = 1
    snapshot = db.scalar(select(ProjectNotionSnapshot).where(
        ProjectNotionSnapshot.project_id == project.id,
        ProjectNotionSnapshot.resource_id == resource).with_for_update().execution_options(populate_existing=True))
    diffs = [] if snapshot is None else list(changes(snapshot.content, current))
    if snapshot is None:
        db.add(ProjectNotionSnapshot(project_id=project.id, resource_id=resource, revision=1, content=current))
    elif diffs:
        snapshot.revision += 1
        for index, (kind, label, before, after) in enumerate(diffs):
            description = (f'수정 전: {before}\n수정 후: {after}' if before is not None and after is not None
                           else f'추가된 내용: {after}' if before is None else f'삭제된 내용: {before}')
            row = api.event(resource, f'content:{snapshot.revision}:{index}',
                            f'{current["title"] or "Notion"} · {label}', description,
                            f'https://www.notion.so/{resource}', timestamp, kind)
            db.add(ProjectActivity(project_id=project.id, source='notion', **row))
        snapshot.content = current
    # Counters count generated change records, not pages or baseline snapshots.
    return {'source': 'notion', 'fetched': len(diffs), 'created': len(diffs), 'existing': 0,
            'has_next': False, 'next_cursor': None}
