import json
from datetime import datetime

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


def no_store(response):
    response.headers['Cache-Control'] = 'no-store'


async def bounded_json(request, schema, max_bytes):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > max_bytes:
            raise HTTPException(413, '전송 내용이 너무 큽니다. 기존 변경사항은 유지됩니다.')
    try:
        return schema.model_validate(json.loads(raw))
    except (ValueError, ValidationError, RecursionError):
        # Validation errors must not echo a pairing code or a document's contents.
        raise HTTPException(422, '플러그인 요청 형식이 올바르지 않습니다.') from None


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
    data = await bounded_json(request, SnapshotRequest, service.MAX_BODY_BYTES)
    return await run_in_threadpool(service.receive, db, credentials.credentials, **data.model_dump())
