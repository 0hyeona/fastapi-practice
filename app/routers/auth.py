"""인증 API 주소와 HTTP 응답을 정의합니다."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.auth import SignupRequest, SignupResponse
from app.services.auth_service import DuplicateUserError, signup

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup_user(request: SignupRequest, db: Session = Depends(get_db)):
    try:
        return signup(db, request)
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
