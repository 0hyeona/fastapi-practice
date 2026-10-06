"""프로젝트 API 라우터. 엔드포인트는 요구사항 확정 후 추가합니다."""

from fastapi import APIRouter

router = APIRouter(prefix="/projects", tags=["projects"])
