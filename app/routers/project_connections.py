"""Connection metadata is derived from projects URLs, without duplicating storage."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.project_activity import ProjectActivity
from app.routers.project_github import owned_project
from app.schemas.project import ProjectLink, ProjectResponse, ProjectUpdate
from app.schemas.project_activity import Source
from app.services.external_sync import resource_id, scoped_token
from app.services.project_github import repository_name, GitHubClient
from app.services.project_service import update_project
from app.services.initial_sync import queue_initial_sync

router = APIRouter(prefix='/api/projects', tags=['project-connections'])


class Connection(BaseModel):
    source: Source
    external_id: str | None
    external_url: str | None
    connection_status: Literal['not_linked', 'invalid_url', 'configuration_required', 'configured', 'public_access_unverified']
    access_verified: bool = False
    detail: str
    unorganized_count: int
    last_activity_stored_at: datetime | None


class Connections(BaseModel):
    project_id: int
    connections: list[Connection]


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_url: ProjectLink | None


def describe_connection(project, source):
    url = getattr(project, source + '_url')
    result = dict(source=source, external_id=None, external_url=url,
                  connection_status='not_linked', detail='등록된 링크가 없습니다.')
    if not url:
        return result
    try:
        identifier = repository_name(url) if source == 'github' else resource_id(source, url)
    except HTTPException:
        return dict(result, connection_status='invalid_url', detail='파일/페이지/저장소 링크 형식을 확인하세요.')
    result['external_id'] = identifier
    if source == 'github':
        authenticated = 'Authorization' in GitHubClient(identifier, project.owner_id).headers
        return dict(result, connection_status='configured' if authenticated else 'public_access_unverified',
                    detail='실제 접근 여부는 동기화 시 확인합니다.' if authenticated else '공개 저장소 조회 모드입니다. 비공개 저장소는 인증 설정이 필요합니다.')
    try:
        scoped_token(source, project.owner_id, identifier)
    except HTTPException as error:
        return dict(result, connection_status='configuration_required', detail=error.detail)
    return dict(result, connection_status='configured', detail='서버 설정 확인 완료. 실제 접근 여부는 동기화 시 확인합니다.')


@router.get('/{project_id}', response_model=ProjectResponse, summary='프로젝트 상세 조회')
def project_detail(project=Depends(owned_project)):
    return project


@router.get('/{project_id}/connections', response_model=Connections, summary='GitHub·Notion·Figma 연결 정보 및 미정리 개수')
def connections(project=Depends(owned_project), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(ProjectActivity.source, func.count()).where(
        ProjectActivity.project_id == project.id, ProjectActivity.story_id.is_(None)
    ).group_by(ProjectActivity.source)).all())
    stored = dict(db.execute(select(ProjectActivity.source, func.max(ProjectActivity.created_at)).where(
        ProjectActivity.project_id == project.id).group_by(ProjectActivity.source)).all())
    return {'project_id': project.id, 'connections': [dict(describe_connection(project, source),
        unorganized_count=counts.get(source, 0), last_activity_stored_at=stored.get(source))
        for source in ('github', 'notion', 'figma')]}


@router.patch('/{project_id}/connections/{source}', response_model=Connections,
              summary='서비스 연결 등록·교체·해제',
              description='external_url에 링크를 입력하면 등록/교체, null이면 해제합니다. 이전에 수집한 활동은 유지됩니다. 인증 설정된 Figma·Notion은 최초 수집을 시도합니다.')
def save_connection(request: ConnectionUpdate, source: Source, background_tasks: BackgroundTasks,
                    project=Depends(owned_project), db: Session = Depends(get_db)):
    url = str(request.external_url) if request.external_url is not None else None
    if url is not None:
        repository_name(url) if source == 'github' else resource_id(source, url)
    updated = update_project(db, project.id, project.owner_id, ProjectUpdate(**{source + '_url': url}))
    if updated is None:
        raise HTTPException(404, 'Project not found.')
    if source in ('figma', 'notion'):
        queue_initial_sync(background_tasks, updated, (source,))
    return connections(updated, db)
