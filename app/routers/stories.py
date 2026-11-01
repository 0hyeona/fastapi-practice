from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user import User
from app.models.story import Story
from app.routers.auth import current_user
from app.schemas.story import StoryCreate, StoryUpdate, StoryResponse, StoryStatus
from app.services import project_content_service as service

router = APIRouter(prefix="/stories", tags=["stories"])


@router.post("", response_model=StoryResponse, status_code=201,
             summary="스토리 작성", description="프로젝트의 작업 내용과 기록을 작성합니다. 초안(draft) 또는 발행(published) 상태로 저장할 수 있습니다.")
def create_record(request: StoryCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.create(db, Story, request, user.id)


@router.get("", response_model=list[StoryResponse], summary="내 스토리 목록 조회",
            description="내 프로젝트의 스토리을 최신순으로 조회합니다. 프로젝트 번호를 생략하면 내 모든 프로젝트를 조회합니다.")
def list_records(
    project_id: int | None = Query(default=None, gt=0, description="조회할 프로젝트 번호 (생략 시 내 전체 프로젝트)"),
    limit: int = Query(default=50, ge=1, le=100, description="조회할 개수 (1~100개)"), offset: int = Query(default=0, ge=0, description="건너뛸 개수 (페이지네이션)"),
    story_status: StoryStatus | None = Query(default=None, description="draft: 초안, published: 발행 (생략 시 전체)"),
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    return service.list_records(db, Story, user.id, project_id, limit, offset, Story.created_at, story_status=story_status)


@router.get("/{story_id}", response_model=StoryResponse, summary="스토리 상세 조회",
            description="내 프로젝트에 속한 스토리 한 건의 상세 정보를 조회합니다.")
def get_record(story_id: int = Path(gt=0, description="스토리 ID"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.get(db, Story, story_id, user.id)


@router.patch("/{story_id}", response_model=StoryResponse, summary="스토리 수정",
              description="전달한 항목만 수정합니다. 프로젝트 번호는 변경할 수 없습니다.")
def update_record(request: StoryUpdate, story_id: int = Path(gt=0, description="스토리 ID"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.update(db, Story, story_id, user.id, request)


@router.delete("/{story_id}", status_code=204, response_class=Response, summary="스토리 삭제",
               description="스토리을 DB에서 영구 삭제합니다. 삭제 후 복구할 수 없습니다.")
def delete_record(story_id: int = Path(gt=0, description="스토리 ID"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    service.delete(db, Story, story_id, user.id)
    return Response(status_code=204)
