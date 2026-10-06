from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.schemas.password_reset import CodeRequest, CodeResponse, EmailRequest, MessageResponse, ResetRequest
from app.services.password_reset_service import RESET_SECONDS, ResetError, find_user, request_code, reset_password, verify_code

router = APIRouter(prefix="/api/auth/password", tags=["password reset"])


def run_action(action, *args):
    try:
        return action(*args)
    except ResetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/check-email", response_model=MessageResponse)
def check_email(request: EmailRequest, db: Session = Depends(get_db)):
    run_action(find_user, db, str(request.email))
    return MessageResponse(message="입력하신 정보와 일치하는 이메일입니다.")


@router.post("/request-code", response_model=MessageResponse)
def send_code(request: EmailRequest, db: Session = Depends(get_db)):
    run_action(request_code, db, str(request.email))
    return MessageResponse(message="인증번호를 이메일로 보냈습니다. 10분 이내에 입력해주세요.")


@router.post("/verify-code", response_model=CodeResponse)
def confirm_code(request: CodeRequest, db: Session = Depends(get_db)):
    token = run_action(verify_code, db, str(request.email), request.code)
    return CodeResponse(reset_token=token, expires_in=RESET_SECONDS)


@router.post("/reset", response_model=MessageResponse)
def change_password(request: ResetRequest, db: Session = Depends(get_db)):
    run_action(reset_password, db, request)
    return MessageResponse(message="비밀번호 변경이 완료되었습니다. 새 비밀번호로 로그인해주세요.")
