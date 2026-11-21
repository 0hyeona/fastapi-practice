"""Collect complete text snapshots and compare stable block IDs."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.project_notion_snapshot import ProjectNotionSnapshot

TEXT_BLOCKS = {
    'paragraph', 'heading_1', 'heading_2', 'heading_3', 'heading_4',
    'bulleted_list_item', 'numbered_list_item', 'quote', 'callout',
    'toggle', 'code', 'to_do', 'template',
}
MEDIA_LABELS = {'image': '이미지', 'video': '동영상', 'audio': '오디오',
                'file': '파일', 'pdf': 'PDF', 'bookmark': '북마크',
                'embed': '임베드', 'link_preview': '링크 미리보기'}
STRUCTURAL_BLOCKS = {'column', 'column_list', 'table', 'synced_block',
                     'divider', 'breadcrumb', 'table_of_contents'}


def rich_text(parts):
    if not isinstance(parts, list):
        raise ValueError("Invalid rich text")
    return ''.join(part['plain_text'] if 'plain_text' in part else part['text']['content'] for part in parts)


def block_text(kind, payload):
    """Missing text fields are read failures, never silently deleted paragraphs."""
    if kind in TEXT_BLOCKS or 'rich_text' in payload:
        text = rich_text(payload['rich_text'])
        if kind == 'to_do':
            if type(payload['checked']) is not bool:
                raise ValueError('Invalid checkbox')
            text = (('[x] ' if payload['checked'] else '[ ] ') + text) if text.strip() else ''
        return text
    if kind == 'table_row':
        cells = [rich_text(cell) for cell in payload['cells']]
        return ' | '.join(cells) if any(cell.strip() for cell in cells) else ''
    if kind in ('child_page', 'child_database'):
        return payload['title']
    if kind == 'equation':
        return payload['expression']
    if kind in MEDIA_LABELS:
        caption = rich_text(payload.get('caption', []))
        # Identify non-text elements without persisting expiring signed URLs.
        return '[' + MEDIA_LABELS[kind] + ']' + (' ' + caption if caption.strip() else '')
    if kind == 'link_to_page':
        return '[페이지 링크]'
    if kind in STRUCTURAL_BLOCKS:
        return ''
    if 'caption' in payload:
        return rich_text(payload['caption'])
    return None


def collect(project, api, db=None):
    resource = api.resource_id('notion', project.notion_url)
    token = api.scoped_token('notion', project.owner_id, resource, db)
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
                text = block_text(kind, payload)
                if text is not None and not isinstance(text, str):
                    raise ValueError('Invalid block text')
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


def comparable_text(block):
    text = block.get('text')
    if isinstance(text, str) and block['type'] in MEDIA_LABELS:
        prefix = '[' + MEDIA_LABELS[block['type']] + ']'
        if not text.startswith(prefix):
            return prefix + (' ' + text if text.strip() else '')
    return text


def changes(before, after):
    if before['title'] != after['title']:
        yield 'title_changed', '제목 변경', before['title'], after['title']
    old, new = before['blocks'], after['blocks']
    for key, block in new.items():
        text = comparable_text(block)
        if text is None:
            continue
        if key not in old:
            if text.strip():
                yield 'content_added', '내용 추가', None, text
        else:
            previous = comparable_text(old[key])
            if previous is None or previous == text or not (previous.strip() or text.strip()):
                continue
            if not previous.strip():
                yield 'content_added', '내용 추가', None, text
            elif not text.strip():
                yield 'content_deleted', '내용 삭제', previous, None
            else:
                yield 'content_updated', '내용 수정', previous, text
    for key, block in old.items():
        if key not in new:
            text = comparable_text(block)
            if text is not None and text.strip():
                yield 'content_deleted', '내용 삭제', text, None


def sync(db, project, progress, api):
    original_url, original_owner = project.notion_url, project.owner_id
    # Serialize collectors before reading remote data so an older fetch cannot
    # overwrite a newer snapshot. record_sync owns commit/rollback of this lock.
    locked = db.scalar(select(Project).where(Project.id == project.id).with_for_update().execution_options(populate_existing=True))
    if locked is None or locked.owner_id != original_owner or locked.notion_url != original_url:
        raise HTTPException(409, 'Project connection changed; retry.')
    resource, current, timestamp = collect(locked, api, db)
    progress['fetched'] = 1
    snapshot = db.scalar(select(ProjectNotionSnapshot).where(
        ProjectNotionSnapshot.project_id == project.id,
        ProjectNotionSnapshot.resource_id == resource).with_for_update().execution_options(populate_existing=True))
    if snapshot is not None:
        for block_id, block in current['blocks'].items():
            previous = snapshot.content['blocks'].get(block_id)
            if block['text'] is None and previous is not None:
                current['blocks'][block_id] = previous
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
    if snapshot is not None:
        # Empty/structural edits still become the next comparison baseline.
        snapshot.content = current
    # Counters count generated change records, not pages or baseline snapshots.
    return {'source': 'notion', 'fetched': len(diffs), 'created': len(diffs), 'existing': 0,
            'has_next': False, 'next_cursor': None}
