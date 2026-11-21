"""Compare immutable Figma versions without a schema change or inferred edits."""
import json
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from app.models.project_activity import ProjectActivity

PREFIX = '이전 버전과 비교한 변경 내용\n'
FIELDS = {
    'name': '이름', 'characters': '텍스트', 'fills': '채우기', 'strokes': '테두리',
    'strokeWeight': '테두리 두께', 'cornerRadius': '모서리', 'rectangleCornerRadii': '모서리',
    'opacity': '불투명도', 'visible': '표시 여부', 'effects': '효과',
    'style': '글꼴 스타일', 'layoutMode': '자동 배치 방향', 'itemSpacing': '항목 간격',
    'paddingLeft': '왼쪽 여백', 'paddingRight': '오른쪽 여백',
    'paddingTop': '위쪽 여백', 'paddingBottom': '아래쪽 여백',
    'primaryAxisAlignItems': '주축 정렬', 'counterAxisAlignItems': '교차축 정렬',
    'componentId': '연결 컴포넌트', 'componentProperties': '컴포넌트 속성',
    'size': '크기', 'position': '위치', 'parent': '상위 요소', 'rotation': '회전',
    'type': '요소 유형', 'styles': '연결 스타일', 'constraints': '제약 조건',
    'characterStyleOverrides': '부분 텍스트 스타일', 'styleOverrideTable': '부분 글꼴 스타일',
}


def normalize(value):
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def flatten(data, *, max_path_bytes=None):
    """Compare own properties; moving a frame must not move every child again."""
    root = data['document']
    if not isinstance(root, dict) or root.get('type') != 'DOCUMENT':
        raise ValueError('Invalid document')
    nodes = {}
    path_bytes = 0
    stack = [(root, None, '', None)]
    while stack:
        node, parent, path, parent_box = stack.pop()
        key = node['id']
        if not isinstance(key, str) or key in nodes or len(nodes) >= 100000:
            raise ValueError('Invalid or oversized document')
        path = (path + ' / ' + node.get('name', node['type'])).strip(' /')
        if max_path_bytes is not None:
            path_bytes += len(path.encode('utf-8'))
            if path_bytes > max_path_bytes:
                raise OverflowError('Figma snapshot paths exceed the comparison budget')
        props = {name: node[name] for name in FIELDS if name in node}
        props['parent'] = parent
        box = node.get('absoluteBoundingBox')
        if box:
            props['size'] = [box['width'], box['height']]
            if parent_box:
                props['position'] = [box['x'] - parent_box['x'], box['y'] - parent_box['y']]
            else:
                props['position'] = [box['x'], box['y']]
        children = node.get('children', [])
        if not isinstance(children, list):
            raise ValueError('Invalid children')
        nodes[key] = {'path': path, 'props': normalize(props),
                      'children': [child['id'] for child in children]}
        stack.extend((child, key, path, box) for child in reversed(children))
    return nodes


def display(value):
    if value is None:
        return '설정 없음'
    if isinstance(value, bool):
        return '표시' if value else '숨김'
    if isinstance(value, str):
        return value[:300] + ('…' if len(value) > 300 else '')
    if isinstance(value, list) and value and all(isinstance(p, dict) and 'type' in p for p in value):
        paints = []
        for paint in value:
            if paint.get('type') == 'SOLID' and 'color' in paint:
                color = paint['color']
                channels = [max(0, min(255, round(color[c] * 255))) for c in ('r', 'g', 'b')]
                paints.append('#' + ''.join(f'{c:02X}' for c in channels)
                              + (f" (불투명도 {paint['opacity']:g})" if paint.get('opacity', 1) != 1 else ''))
            else:
                paints.append(json.dumps(paint, ensure_ascii=False, sort_keys=True))
        return ', '.join(paints)[:350]
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(', ', ': '))[:350]


def describe(before, after):
    old, new = flatten(before), flatten(after)
    return describe_nodes(old, new, before.get('name'), after.get('name'))


def describe_nodes(old, new, before_name, after_name, *, prefix=PREFIX, basis=None):
    additions, deletions, edits = [], [], []
    for key, node in new.items():
        if key not in old:
            additions.append(key)
            continue
        changes = [(label, old[key]['props'].get(field), node['props'].get(field))
                   for field, label in FIELDS.items()
                   if old[key]['props'].get(field) != node['props'].get(field)]
        old_children, new_children = old[key]['children'], node['children']
        if old_children != new_children and set(old_children) == set(new_children):
            changes.append(('하위 요소 순서', old_children, new_children))
        if changes:
            edits.append((node['path'], changes))
    deletions = [key for key in old if key not in new]
    lines = [prefix.rstrip(), f'요소 추가 {len(additions)}개 · 삭제 {len(deletions)}개 · 수정 {len(edits)}개']
    if before_name != after_name:
        lines.append(f"파일 이름: {display(before_name)} → {display(after_name)}")
    entries = []
    for keys, nodes, other, label in ((additions, new, old, '추가'), (deletions, old, new, '삭제')):
        for key in keys:
            # One line for an added/removed subtree, rather than its every child.
            if nodes[key]['props']['parent'] not in other and nodes[key]['props']['parent'] is not None:
                continue
            entries.append(f"{label}: {nodes[key]['path']}")
    for path, changes in edits:
        entries.append(path + '\n' + '\n'.join(
            f'{label}: {display(previous)} → {display(current)}' for label, previous, current in changes))
    if not entries and before_name == after_name:
        lines.append('비교한 텍스트·스타일·크기·위치·구조 속성에서는 차이가 발견되지 않았어요. 이미지 픽셀과 벡터 경로의 변화는 비교하지 않아요.')
    displayed = 0
    for entry in entries[:30]:
        if sum(len(line) for line in lines) + len(entry) > 18000:
            break
        lines.append(entry)
        displayed += 1
    if len(entries) > displayed:
        lines.append('표시 분량을 넘어선 변경 항목은 생략했어요.')
    lines.append(basis or '비교 기준: 이 기록의 직전 저장 버전. 이미지 픽셀·벡터 경로는 비교 대상에서 제외돼요.')
    return '\n\n'.join(lines).replace(prefix.rstrip() + '\n\n', prefix, 1)


def enrich(rows, revisions, project, api, db, resource, headers, current=None, has_older=False):
    """At most two comparisons / three historical reads; descriptions are the cache."""
    if db is None:
        return
    existing = {row.external_id: row for row in db.scalars(select(ProjectActivity).where(
        ProjectActivity.project_id == project.id, ProjectActivity.source == 'figma',
        ProjectActivity.external_id.in_([row['external_id'] for row in rows]))).all()}
    versions = sorted(revisions.values(), key=lambda item: api.occurred_at(item['created_at']), reverse=True)
    by_revision = {item['id']: index for index, item in enumerate(versions)}
    # The current-file response was fetched with depth=1 and is metadata only.
    # It must never be compared as if it were a complete document.
    cache = {}
    endpoint = f'https://api.figma.com/v1/files/{resource}'
    budget = 2

    def load(revision):
        if revision not in cache:
            payload = api.fetch_json('figma', endpoint, headers, {'version': revision})
            if str(payload.get('version')) != revision:
                raise ValueError('Wrong Figma version')
            flatten(payload)  # Reject partial/malformed responses before caching.
            cache[revision] = payload
        return cache[revision]

    ordered = sorted(rows, key=lambda row: row['occurred_at'], reverse=True)
    for row in ordered:
        saved = existing.get(row['external_id'])
        if saved is not None and (saved.story_id is not None or (saved.description or '').startswith(PREFIX)):
            continue
        revision = parse_qs(urlsplit(row['source_url']).query).get('version-id', [None])[0]
        if revision is None and current is not None:
            revision = str(current['version'])
        index = by_revision.get(revision)
        if index is None:
            continue
        if index + 1 >= len(versions):
            if not has_older:
                original = row['description']
                row['description'] = PREFIX + '비교할 이전 저장 버전이 없는 최초 기록이에요.'
                if original:
                    row['description'] += '\n\n버전 설명:\n' + original[:2000]
            continue
        if budget == 0:
            continue
        previous = versions[index + 1]['id']
        # Same timestamps do not prove ordering; do not invent a previous version.
        if api.occurred_at(versions[index]['created_at']) == api.occurred_at(versions[index + 1]['created_at']):
            continue
        budget -= 1
        original = row['description']
        row['description'] = describe(load(previous), load(revision))
        if original and original not in ('현재 파일의 수정 상태',):
            row['description'] += '\n\n버전 작성자가 남긴 설명:\n' + original[:2000]
        # MySQL TEXT is limited in bytes, including four-byte emoji.
        row['description'] = row['description'].encode('utf-8')[:60000].decode('utf-8', errors='ignore')
