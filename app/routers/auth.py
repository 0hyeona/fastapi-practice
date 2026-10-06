"""인증 API 주소와 HTTP 응답을 정의합니다."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.auth_service import (
    DuplicateUserError, InvalidCredentialsError, authenticated_session, login, logout, signup,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_login_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                      db: Session = Depends(get_db)):
    if credentials is None:
        raise unauthorized("로그인이 필요합니다.")
    try:
        return authenticated_session(db, credentials.credentials)
    except InvalidCredentialsError as exc:
        raise unauthorized(str(exc)) from exc


@router.post("/login", response_model=LoginResponse)
def login_user(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        return login(db, request)
    except InvalidCredentialsError as exc:
        raise unauthorized(str(exc)) from exc


@router.get("/me", response_model=SignupResponse)
def current_user(login_session=Depends(get_login_session)):
    return login_session[1]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(login_session=Depends(get_login_session), db: Session = Depends(get_db)):
    logout(db, login_session[0])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup_user(request: SignupRequest, db: Session = Depends(get_db)):
    try:
        return signup(db, request)
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
