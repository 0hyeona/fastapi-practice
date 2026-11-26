import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database.database import get_db
from app.routers.auth import current_user
from app.routers.project_github import accessible_project, owned_project
from app.services import figma_plugin as service

router = APIRouter(tags=['figma-plugin'])
bearer = HTTPBearer(auto_error=False)


class PluginStatus(BaseModel):
    enabled: bool
    connected: bool
    expires_at: datetime | None
    last_received_at: datetime | None
    last_seen_at: datetime | None = None
    collection_state: str = 'offline'


class PairRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: SecretStr = Field(min_length=40, max_length=128)
    file_url: str = Field(min_length=1, max_length=2048)


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    file_url: str = Field(min_length=1, max_length=2048)
    name: str = Field(max_length=255)
    document: dict


class DeltaRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: int = Field(strict=True, ge=1, le=2147483647)
    file_url: str = Field(min_length=1, max_length=2048)
    name: str = Field(max_length=255)
    base_revision: int = Field(strict=True, ge=0)
    upserts: list[dict] = Field(max_length=100000)
    deleted: list[str] = Field(max_length=100000)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_url: str = Field(min_length=1, max_length=2048)
    state: Literal['collecting', 'sending', 'error', 'paused'] = 'collecting'


def no_store(response):
    response.headers['Cache-Control'] = 'no-store'


async def bounded_body(request, max_bytes):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > max_bytes:
            raise HTTPException(413, '전송 내용이 요청 크기 한도를 초과했어요.')
        raw.extend(chunk)
    return raw


def parse_payload(raw, schema):
    try:
        return schema.model_validate(json.loads(raw))
    except (ValueError, ValidationError, RecursionError):
        # Validation errors must not echo a pairing code or a document's contents.
        raise HTTPException(422, '플러그인 요청 형식이 올바르지 않습니다.') from None


async def bounded_json(request, schema, max_bytes):
    return parse_payload(await bounded_body(request, max_bytes), schema)


def receive_body(db, token, body, compressed):
    if compressed:
        body = service.decode_upload(db, token, body)
    data = parse_payload(body, SnapshotRequest)
    return service.receive(db, token, data.sequence, data.file_url, data.name, data.document)


@router.get('/api/projects/{project_id}/figma/plugin', response_model=PluginStatus)
def status(response: Response, project=Depends(accessible_project), db: Session = Depends(get_db)):
    no_store(response)
    return service.status(db, project)


@router.post('/api/projects/{project_id}/figma/plugin/pairing', summary='프로젝트 소유자의 일회용 플러그인 연결 코드')
def create_pairing(response: Response, project=Depends(owned_project), user=Depends(current_user),
                   db: Session = Depends(get_db)):
    no_store(response)
    return service.create_pairing(db, project, user.id)


@router.delete('/api/projects/{project_id}/figma/plugin', response_model=PluginStatus)
def disconnect(response: Response, project=Depends(owned_project), user=Depends(current_user),
               db: Session = Depends(get_db)):
    no_store(response)
    return service.disconnect(db, project, user.id)


@router.post('/api/figma-plugin/pair', summary='편집기에서 일회용 코드 사용')
async def pair(request: Request, response: Response, db: Session = Depends(get_db)):
    no_store(response)
    data = await bounded_json(request, PairRequest, 8192)
    return await run_in_threadpool(service.pair, db, data.code.get_secret_value(), data.file_url)


@router.post('/api/figma-plugin/snapshot', summary='편집기의 현재 상태 전송 (Figma REST 호출 없음)')
async def snapshot(request: Request, response: Response, credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                   db: Session = Depends(get_db)):
    no_store(response)
    if credentials is None or not credentials.credentials.startswith('moeum_figma_plugin_'):
        raise HTTPException(401, '플러그인 연결이 필요합니다.')
    body = await bounded_body(request, service.MAX_BODY_BYTES)
    media_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    return await run_in_threadpool(receive_body, db, credentials.credentials, body, media_type == 'application/gzip')


@router.post('/api/figma-plugin/resume', summary='저장한 플러그인 인증 재사용 및 상태 알림')
async def resume(request: Request, response: Response, credentials=Depends(bearer), db: Session = Depends(get_db)):
    no_store(response)
    if credentials is None:
        raise HTTPException(401, '플러그인 연결이 필요합니다.')
    data = await bounded_json(request, ResumeRequest, 8192)
    return await run_in_threadpool(service.resume, db, credentials.credentials, data.file_url, data.state)


def receive_delta(db, token, raw, compressed):
    if compressed:
        raw = service.decode_upload(db, token, raw)
    data = parse_payload(raw, DeltaRequest)
    return service.receive(db, token, data.sequence, data.file_url, data.name, None,
                           delta={'upserts': data.upserts, 'deleted': data.deleted}, base_revision=data.base_revision)


@router.post('/api/figma-plugin/changes', summary='변경된 요소만 배치 전송')
async def changes(request: Request, response: Response, credentials=Depends(bearer), db: Session = Depends(get_db)):
    no_store(response)
    if credentials is None:
        raise HTTPException(401, '플러그인 연결이 필요합니다.')
    raw = await bounded_body(request, service.MAX_BODY_BYTES)
    return await run_in_threadpool(receive_delta, db, credentials.credentials, raw,
                                  request.headers.get('content-type', '').split(';')[0].strip().lower() == 'application/gzip')
