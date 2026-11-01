from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user import User
from app.models.project_activity import ProjectActivity
from app.routers.auth import current_user
from app.schemas.project_activity import ProjectActivityCreate, ProjectActivityUpdate, ProjectActivityResponse, Source
from app.services import project_content_service as service

router = APIRouter(prefix="/project_activities", tags=["project_activities"])


@router.post("", response_model=ProjectActivityResponse, status_code=201,
             summary="프로젝트 변경사항 등록", description="GitHub·Figma·Notion 변경사항을 등록합니다. 외부 서비스에서 자동으로 수집하는 기능은 아닙니다.")
def create_record(request: ProjectActivityCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.create(db, ProjectActivity, request, user.id)


@router.get("", response_model=list[ProjectActivityResponse], summary="내 프로젝트 변경사항 목록 조회",
            description="내 프로젝트의 프로젝트 변경사항을 최신순으로 조회합니다. 프로젝트 번호를 생략하면 내 모든 프로젝트를 조회합니다.")
def list_records(
    unorganized: bool | None = Query(default=None, description="true: unorganized, false: linked to Story"),
    project_id: int | None = Query(default=None, gt=0, description="조회할 프로젝트 번호 (생략 시 내 전체 프로젝트)"),
    limit: int = Query(default=50, ge=1, le=100, description="조회할 개수 (1~100개)"), offset: int = Query(default=0, ge=0, description="건너뛸 개수 (페이지네이션)"),
    source: Source | None = Query(default=None, description="변경사항 출처: github / figma / notion (생략 시 전체)"),
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    return service.list_records(db, ProjectActivity, user.id, project_id, limit, offset, ProjectActivity.occurred_at, source=source, unorganized=unorganized)


@router.get("/{activity_id}", response_model=ProjectActivityResponse, summary="프로젝트 변경사항 상세 조회",
            description="내 프로젝트에 속한 프로젝트 변경사항 한 건의 상세 정보를 조회합니다.")
def get_record(activity_id: int = Path(gt=0, description="활동 내역 ID"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.get(db, ProjectActivity, activity_id, user.id)


@router.patch("/{activity_id}", response_model=ProjectActivityResponse, summary="프로젝트 변경사항 수정",
              description="전달한 항목만 수정합니다. 프로젝트 번호는 변경할 수 없습니다.")
def update_record(request: ProjectActivityUpdate, activity_id: int = Path(gt=0, description="활동 내역 ID"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.update(db, ProjectActivity, activity_id, user.id, request)


@router.delete("/{activity_id}", status_code=204, response_class=Response, summary="프로젝트 변경사항 삭제",
               description="프로젝트 변경사항을 DB에서 영구 삭제합니다. 삭제 후 복구할 수 없습니다.")
def delete_record(activity_id: int = Path(gt=0, description="활동 내역 ID"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    service.delete(db, ProjectActivity, activity_id, user.id)
    return Response(status_code=204)
