from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.routers.auth import current_user
from app.services import notion_oauth as service

router = APIRouter(prefix='/api/integrations/notion', tags=['notion-oauth'])


class AuthorizationURL(BaseModel):
    authorization_url: str


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: SecretStr = Field(min_length=1, max_length=2048)
    state: SecretStr = Field(min_length=20, max_length=128)


class NotionStatus(BaseModel):
    connected: bool
    workspace_id: str | None
    workspace_name: str | None


@router.post('/authorize', response_model=AuthorizationURL, summary='내 Notion 연결 승인 URL 생성')
def authorize(user=Depends(current_user), db: Session = Depends(get_db)):
    return service.authorize(db, user.id)


@router.post('/exchange', response_model=NotionStatus, summary='Notion 승인 코드 교환 및 내 연결 저장')
def exchange(request: ExchangeRequest, user=Depends(current_user), db: Session = Depends(get_db)):
    return service.exchange(db, user.id, request.code.get_secret_value(), request.state.get_secret_value())


@router.get('', response_model=NotionStatus, summary='내 Notion 계정 연결 상태')
def status(user=Depends(current_user), db: Session = Depends(get_db)):
    return service.status(db, user.id)


@router.post('/refresh', response_model=NotionStatus, summary='내 Notion 토큰 갱신')
def refresh(user=Depends(current_user), db: Session = Depends(get_db)):
    return service.refresh(db, user.id)
