"""인증 API 주소와 HTTP 응답을 정의합니다."""

import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.auth_service import (
    DuplicateUserError, InvalidCredentialsError, authenticated_session, login, logout, signup,
)
from app.services.github_oauth import fetch_github_user
from app.services.github_login import github_login_session

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


@router.get("/github/login")
def github_login(request: Request):
    client_id = os.getenv("GITHUB_CLIENT_ID")
    redirect_uri = os.getenv("GITHUB_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub 로그인 설정이 필요합니다.",
        )
    state = secrets.token_urlsafe(32)
    query = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    })
    response = RedirectResponse(f"https://github.com/login/oauth/authorize?{query}")
    response.set_cookie(
        "github_oauth_state", state, max_age=600, httponly=True,
        secure=request.url.scheme == "https", samesite="lax", path="/api/auth/github",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/github/callback", response_model=LoginResponse)
async def github_callback(request: Request, code: str | None = None,
                          state: str | None = None, error: str | None = None,
                          db: Session = Depends(get_db)):
    expected_state = request.cookies.get("github_oauth_state")
    try:
        if not state or not expected_state or not secrets.compare_digest(state.encode(), expected_state.encode()):
            raise HTTPException(400, "GitHub 로그인 요청을 확인할 수 없습니다. 로그인부터 다시 시작하세요.")
        if error:
            raise HTTPException(400, "GitHub 로그인이 취소되었거나 승인되지 않았습니다.")
        if not code:
            raise HTTPException(400, "GitHub 인증 코드가 없습니다.")
        user = await fetch_github_user(code)
        # 명시적으로 설정한 로컬 테스트에서만 이메일 중복을 우회합니다.
        test_email = os.getenv("GITHUB_TEST_EMAIL") if request.url.hostname in {"localhost", "127.0.0.1"} else None
        session = github_login_session(db, user, test_email=test_email)
        response = JSONResponse(session.model_dump(mode="json"))
    except InvalidCredentialsError as exc:
        response = JSONResponse({"detail": str(exc)}, status_code=403)
    except SQLAlchemyError:
        db.rollback()
        response = JSONResponse({"detail": "회원 로그인 정보를 저장하지 못했습니다. 잠시 후 다시 시도하세요."}, status_code=503)
    except HTTPException as exc:
        response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    response.delete_cookie("github_oauth_state", path="/api/auth/github")
    response.headers["Cache-Control"] = "no-store"
    return response


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
