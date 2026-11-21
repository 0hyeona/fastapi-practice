from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.routers.project_github import owned_project, accessible_project
from app.services.external_sync import connection_state, sync_external

router = APIRouter(prefix='/api/projects', tags=['external-integrations'])


class ExternalSyncResult(BaseModel):
    source: Literal['figma', 'notion']
    fetched: int
    created: int
    existing: int
    has_next: bool
    next_cursor: str | None


class ConnectionState(BaseModel):
    linked: bool
    configured: bool
    resource_id: str | None
    detail: str


@router.get('/{project_id}/figma/sync-status')
def figma_sync_status(project=Depends(accessible_project), db: Session = Depends(get_db)):
    from app.services.figma_sync_policy import state
    from app.services.figma_plugin import status
    plugin = status(db, project)
    return {**state(db, project.id), 'transport': 'plugin' if plugin['enabled'] else 'rest', 'plugin': plugin}


@router.get('/{project_id}/integrations', response_model=dict[str, ConnectionState], summary='Figma·Notion 연결 설정 확인')
def integrations(project=Depends(accessible_project), db: Session = Depends(get_db)):
    return {source: connection_state(project, source, db) for source in ('figma', 'notion')}


@router.post('/{project_id}/figma/sync', response_model=ExternalSyncResult, summary='Figma 버전 변경사항 수집',
             description='현재 파일 버전과 버전 기록 한 페이지를 저장합니다. has_next=true이면 next_cursor를 cursor로 전달하세요.')
def sync_figma(project=Depends(owned_project), db: Session = Depends(get_db),
               cursor: str | None = Query(None, min_length=1, max_length=2048)):
    from app.services.figma_plugin import status
    if status(db, project)['enabled']:
        # Refreshing a live connection reads saved activities. Editor pushes are
        # independent of REST history and must not erase an active REST cooldown.
        return {'source': 'figma', 'fetched': 0, 'created': 0, 'existing': 0,
                'has_next': False, 'next_cursor': None}
    return sync_external(db, project, 'figma', cursor)


@router.post('/{project_id}/notion/sync', response_model=ExternalSyncResult, summary='Notion 페이지 수정사항 수집',
             description='연결된 페이지 한 개의 최근 수정 상태를 저장합니다. 전체 과거 편집 이력, 하위 페이지 및 데이터베이스 항목 수집은 포함하지 않습니다.')
def sync_notion(project=Depends(accessible_project), db: Session = Depends(get_db)):
    return sync_external(db, project, 'notion')
