"""Receive editor snapshots without calling the Figma REST API.

Pairing codes are single use; plugin tokens authorize only one owner's project
and file. Neither credential is a MOEUM login token or a Figma OAuth token.
"""
import base64
import gzip
import hashlib
import json
import logging
import secrets
import zlib
from datetime import timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.figma_plugin import FigmaPluginConnection, ProjectFigmaSnapshot
from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.project_sync_run import ProjectSyncRun
from app.models.user import User
from app.services.auth_service import hash_token, utc_now
from app.services.external_sync import resource_id
from app.services.figma_version_diff import describe_nodes, flatten

MAX_BODY_BYTES = 4 * 1024 * 1024  # Wire body and maximum stored JSON envelope.
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_NORMALIZED_BYTES = 48 * 1024 * 1024
PLAIN_STORAGE_BYTES = 256 * 1024
STORAGE_ENCODING = 'gzip-json-v1'
PAIR_LIFETIME = timedelta(minutes=10)
SESSION_LIFETIME = timedelta(hours=8)  # Absolute session expiry; reconnect with a new code.
PREFIX = '마지막 전송과 비교한 변경 내용\n'
logger = logging.getLogger(__name__)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value else None


def connection(db, project_id, locked=False):
    query = select(FigmaPluginConnection).where(FigmaPluginConnection.project_id == project_id)
    if locked:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def same_file(project, row):
    if not row or project.owner_id != row.user_id:
        return False
    try:
        return resource_id('figma', project.figma_url) == row.resource_id
    except HTTPException:
        return False


def status(db, project):
    row = connection(db, project.id)
    valid = same_file(project, row) and row.enabled
    connected = bool(valid and row.token_hash and row.expires_at and row.expires_at > utc_now())
    return {'enabled': bool(valid),
            'connected': connected,
            'expires_at': utc(row.expires_at) if valid else None,
            'last_received_at': utc(row.last_received_at) if valid else None,
            'last_seen_at': utc(row.last_seen_at) if valid else None,
            'collection_state': (row.collection_state or 'offline') if connected and row.last_seen_at and
                                 row.last_seen_at > utc_now() - timedelta(seconds=75) else 'offline'}


def locked_project(db, project_id):
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update()
                        .execution_options(populate_existing=True))
    if project is None:
        raise HTTPException(404, '프로젝트를 찾을 수 없습니다.')
    return project


def create_pairing(db, project, user_id):
    try:
        project = locked_project(db, project.id)
        if project.owner_id != user_id:
            raise HTTPException(403, '프로젝트 소유자만 실시간 연결을 설정할 수 있습니다.')
        resource = resource_id('figma', project.figma_url)
        row = connection(db, project.id, locked=True)
        if row is None:
            row = FigmaPluginConnection(project_id=project.id)
            db.add(row)
        code = 'moeum_pair_' + secrets.token_urlsafe(32)
        row.user_id, row.resource_id, row.enabled = user_id, resource, True
        row.pairing_hash = hash_token(code)
        row.pairing_expires_at = utc_now() + PAIR_LIFETIME
        # A new code explicitly replaces the previous editor session.
        row.token_hash = None
        row.expires_at = None
        row.last_sequence = 0
        # Keep the last successful collection time when replacing credentials.
        row.last_seen_at = None
        row.collection_state = 'paused'
        result = {'code': code, 'expires_at': utc(row.pairing_expires_at),
                  'project_name': project.project_name, 'file_url': project.figma_url}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def pair(db, code, file_url):
    try:
        digest = hash_token(code)
        candidate = db.scalar(select(FigmaPluginConnection).where(FigmaPluginConnection.pairing_hash == digest))
        if candidate is None:
            raise HTTPException(401, '연결 코드가 만료되었거나 이미 사용됐습니다. 모음에서 새 코드를 만드세요.')
        project = locked_project(db, candidate.project_id)
        row = connection(db, project.id, locked=True)
        if (not same_file(project, row) or not row.enabled or row.pairing_hash != digest
                or not row.pairing_expires_at or row.pairing_expires_at <= utc_now()):
            raise HTTPException(401, '연결 코드가 만료되었거나 이미 사용됐습니다. 모음에서 새 코드를 만드세요.')
        user = db.get(User, row.user_id)
        if user is None or user.account_status != 'active':
            raise HTTPException(401, '모음 계정을 확인하고 다시 연결하세요.')
        if resource_id('figma', file_url) != row.resource_id:
            raise HTTPException(409, '현재 파일의 공유 링크가 프로젝트에 등록한 Figma 파일과 다릅니다.')
        token = 'moeum_figma_plugin_' + secrets.token_urlsafe(32)
        row.token_hash = hash_token(token)
        row.expires_at = utc_now() + SESSION_LIFETIME
        row.last_seen_at = utc_now()
        row.collection_state = 'collecting'
        row.pairing_hash = row.pairing_expires_at = None
        row.last_sequence = 0
        result = {'token': token, 'expires_at': utc(row.expires_at), 'project_id': project.id,
                  'project_name': project.project_name, 'file_url': project.figma_url}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def disconnect(db, project, user_id):
    try:
        project = locked_project(db, project.id)
        if project.owner_id != user_id:
            raise HTTPException(403, '프로젝트 소유자만 연결을 해제할 수 있습니다.')
        row = connection(db, project.id, locked=True)
        if row:
            row.enabled = False
            row.collection_state = 'paused'
            row.token_hash = row.pairing_hash = None
            row.expires_at = row.pairing_expires_at = None
        db.commit()
        return status(db, project)
    except Exception:
        db.rollback()
        raise


def decompress_limited(data, limit):
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    raw = decoder.decompress(data, limit + 1)
    if len(raw) > limit or decoder.unconsumed_tail:
        raise OverflowError('Uncompressed snapshot is too large')
    if not decoder.eof or decoder.unused_data:
        raise ValueError('Incomplete or trailing gzip data')
    return raw


def decode_upload(db, token, body):
    # Do not expand large uploads until their editor session has been checked.
    row = db.scalar(select(FigmaPluginConnection).where(
        FigmaPluginConnection.token_hash == hash_token(token),
        FigmaPluginConnection.enabled.is_(True),
        FigmaPluginConnection.expires_at > utc_now()))
    if row is None:
        raise HTTPException(401, '플러그인 연결이 만료됐습니다. 모음에서 새 연결 코드를 만드세요.')
    try:
        return decompress_limited(body, MAX_DOCUMENT_BYTES)
    except OverflowError:
        raise HTTPException(413, '디자인 데이터가 압축 전 한도 32 MiB를 초과했어요.') from None
    except (ValueError, zlib.error):
        raise HTTPException(422, '압축된 디자인 데이터를 읽지 못했어요.') from None


def previous_content(stored):
    if 'encoding' not in stored:
        return stored
    try:
        if stored['encoding'] != STORAGE_ENCODING:
            raise ValueError('Unsupported snapshot encoding')
        packed = base64.b64decode(stored['data'], validate=True)
        return json.loads(decompress_limited(packed, MAX_NORMALIZED_BYTES))
    except (KeyError, TypeError, ValueError, OverflowError, zlib.error):
        raise HTTPException(500, '저장된 비교 기준을 읽지 못했습니다. 기존 기록은 유지됩니다.') from None


def normalize_snapshot(name, document):
    try:
        nodes = flatten({'document': document}, max_path_bytes=MAX_NORMALIZED_BYTES)
        # Non-finite numbers must never enter a JSON database or comparison.
        content = {'name': name, 'nodes': nodes}
        serialized = json.dumps(content, ensure_ascii=False, sort_keys=True,
                                separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(serialized) > MAX_NORMALIZED_BYTES:
            raise OverflowError('Normalized snapshot is too large')
        return content, hashlib.sha256(serialized).hexdigest(), serialized
    except OverflowError:
        raise HTTPException(413, '전체 요소의 비교 데이터가 48 MiB를 초과했어요.') from None
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
        raise HTTPException(422, '완전한 Figma 문서 형식이 아닙니다. 기존 변경사항은 유지됩니다.') from None


def storage_content(content, serialized):
    if len(serialized) <= PLAIN_STORAGE_BYTES:
        return content
    packed = base64.b64encode(gzip.compress(serialized, compresslevel=4, mtime=0)).decode('ascii')
    if len(packed) + 128 > MAX_BODY_BYTES:
        raise HTTPException(413, '압축한 비교 기준이 저장 한도 4 MiB를 초과했어요.')
    return {'encoding': STORAGE_ENCODING, 'data': packed}


def receive(db, token, sequence, file_url, name, document, delta=None, base_revision=None):
    verified_project_id = None
    try:
        digest = hash_token(token)
        candidate = db.scalar(select(FigmaPluginConnection).where(FigmaPluginConnection.token_hash == digest))
        if candidate is None:
            raise HTTPException(401, '플러그인 연결이 만료됐습니다. 모음에서 새 연결 코드를 만드세요.')
        project = locked_project(db, candidate.project_id)
        row = connection(db, project.id, locked=True)
        if (not same_file(project, row) or not row.enabled or row.token_hash != digest
                or not row.expires_at or row.expires_at <= utc_now()):
            raise HTTPException(401, '플러그인 연결이 만료되었거나 프로젝트 파일이 바뀌었습니다. 다시 연결하세요.')
        user = db.get(User, row.user_id)
        if user is None or user.account_status != 'active':
            raise HTTPException(401, '사용할 수 없는 모음 계정입니다.')
        if resource_id('figma', file_url) != row.resource_id:
            raise HTTPException(409, '이 연결로 다른 Figma 파일의 변경사항을 보낼 수 없습니다.')
        verified_project_id = project.id
        if sequence <= row.last_sequence:
            saved = db.get(ProjectFigmaSnapshot, project.id)
            result = {'created': 0, 'baseline': False, 'duplicate': True,
                      'received_at': utc(row.last_received_at), 'last_sequence': row.last_sequence,
                      'revision': saved.revision if saved else 0}
            db.rollback()
            return result
        snapshot = db.scalar(select(ProjectFigmaSnapshot).where(ProjectFigmaSnapshot.project_id == project.id)
                             .with_for_update().execution_options(populate_existing=True))
        if delta is not None:
            if snapshot is None or snapshot.resource_id != row.resource_id or snapshot.revision != base_revision:
                raise HTTPException(409, '비교 기준이 바뀌었습니다. 현재 파일을 다시 비교하세요.')
            document = apply_delta(previous_content(snapshot.content), delta)
        content, fingerprint, serialized = normalize_snapshot(name, document)
        baseline = snapshot is None or snapshot.resource_id != row.resource_id
        changed = not baseline and snapshot.fingerprint != fingerprint
        timestamp = utc_now()
        if changed:
            previous = previous_content(snapshot.content)
            description = describe_nodes(previous['nodes'], content['nodes'],
                                         previous['name'], name, prefix=PREFIX,
                                         basis='비교 기준: 플러그인이 마지막으로 전송한 상태. 여러 편집은 한 변경사항으로 묶어요.')
            description = description.encode('utf-8')[:60000].decode('utf-8', errors='ignore')
            from app.services.external_sync import event
            revision = snapshot.revision + 1
            activity = event(row.resource_id, f'plugin:{revision}:{fingerprint}',
                             f'{name or "Figma"} · 디자인 변경', description,
                             f'https://www.figma.com/design/{row.resource_id}',
                             timestamp.replace(tzinfo=timezone.utc).isoformat(), 'design_updated')
            db.add(ProjectActivity(project_id=project.id, source='figma', **activity))
        if snapshot is None:
            snapshot = ProjectFigmaSnapshot(project_id=project.id, revision=0)
            db.add(snapshot)
        # Never reset the revision when changing files: switching A -> B -> A must
        # not reuse an external ID from a previous editing session.
        snapshot.revision += int(changed or baseline)
        snapshot.resource_id = row.resource_id
        snapshot.fingerprint = fingerprint
        if changed or baseline:
            snapshot.content = storage_content(content, serialized)
        snapshot.received_at = timestamp
        row.last_received_at = timestamp
        row.last_seen_at = timestamp
        row.collection_state = 'collecting'
        row.last_sequence = sequence
        db.commit()
        return {'created': int(changed), 'baseline': baseline, 'duplicate': False,
                'received_at': utc(timestamp), 'revision': snapshot.revision, 'last_sequence': sequence}
    except Exception as error:
        db.rollback()
        if verified_project_id is not None:
            record_failure(db, verified_project_id, digest, error)
        raise


def record_failure(db, project_id, digest, error):
    """Keep safe diagnostics in existing sync history, without changing the baseline."""
    code = error.status_code if isinstance(error, HTTPException) else 500
    reasons = {409: 'Comparison baseline changed; reconcile the current file.',
               413: 'Snapshot exceeds the storage limit.',
               422: 'Invalid design data.'}
    message = 'Figma plugin: ' + reasons.get(code, 'Storage failed; retry the same batch.')
    try:
        project = locked_project(db, project_id)
        row = connection(db, project_id, locked=True)
        if not same_file(project, row) or not row.enabled or row.token_hash != digest:
            db.rollback()
            return
        timestamp = utc_now()
        row.last_seen_at = timestamp
        row.collection_state = 'error'
        db.add(ProjectSyncRun(project_id=project_id, source='figma', status='failed',
                              started_at=timestamp, finished_at=timestamp,
                              fetched=0, created=0, existing=0, error_code=code,
                              error_message=message))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning('Unable to record Figma plugin failure for project %s (HTTP %s)', project_id, code)


def resume(db, token, file_url, state='collecting'):
    """Revalidate owner, account, file and revocation on every heartbeat."""
    try:
        digest = hash_token(token)
        candidate = db.scalar(select(FigmaPluginConnection).where(FigmaPluginConnection.token_hash == digest))
        if candidate is None:
            raise HTTPException(401, '플러그인을 다시 연결하세요.')
        project = locked_project(db, candidate.project_id)
        row = connection(db, project.id, locked=True)
        if (not same_file(project, row) or not row.enabled or row.token_hash != digest
                or not row.expires_at or row.expires_at <= utc_now()):
            raise HTTPException(401, '플러그인 연결이 만료되거나 해제됐습니다.')
        user = db.get(User, row.user_id)
        if user is None or user.account_status != 'active':
            raise HTTPException(401, '사용할 수 없는 계정입니다.')
        if resource_id('figma', file_url) != row.resource_id:
            raise HTTPException(409, '연결한 파일과 현재 파일이 다릅니다.')
        row.last_seen_at = utc_now()
        row.collection_state = state
        snapshot = db.get(ProjectFigmaSnapshot, project.id)
        result = {'project_id': project.id, 'project_name': project.project_name,
                  'last_sequence': row.last_sequence, 'revision': snapshot.revision if snapshot else 0,
                  'expires_at': utc(row.expires_at)}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def apply_delta(previous, delta):
    """Apply bounded node upserts atomically to the existing comparison baseline."""
    nodes = {key: dict(value['props'], id=key, children=list(value['children']))
             for key, value in previous['nodes'].items()}
    def remove(key):
        node = nodes.pop(key, None)
        if node:
            for child in node['children']:
                remove(child)
    try:
        for key in delta['deleted']:
            remove(key)
        for node in delta['upserts']:
            if not isinstance(node.get('id'), str) or not isinstance(node.get('children', []), list):
                raise ValueError()
            nodes[node['id']] = node
        roots = [key for key, node in nodes.items() if node.get('type') == 'DOCUMENT']
        if len(roots) != 1 or len(nodes) > 100000:
            raise ValueError()
        visited = set()
        def build(key, depth=0):
            if depth > 100 or key in visited:
                raise ValueError()
            visited.add(key)
            node = dict(nodes[key])
            node['children'] = [build(child, depth + 1) for child in node.get('children', [])]
            return node
        document = build(roots[0])
        if len(visited) != len(nodes):
            raise ValueError()
        return document
    except (KeyError, TypeError, ValueError, RecursionError):
        raise HTTPException(409, '요소 구조를 다시 비교해야 합니다. 전체 보완 수집을 실행하세요.') from None
