"""발신 Gmail 계정의 OAuth 권한으로 인증번호를 발송합니다."""

import base64
import logging
import os
import ssl
from email.message import EmailMessage

import httpx

logger = logging.getLogger(__name__)


def google_error_reason(response: httpx.Response) -> str:
    """정해진 오류 코드만 기록하고 Google 원문/개인정보는 기록하지 않습니다."""
    allowed = {
        "invalid_grant", "invalid_client", "unauthorized_client", "invalid_scope",
        "access_denied", "insufficientPermissions", "accessNotConfigured",
        "forbidden", "authError", "dailyLimitExceeded", "rateLimitExceeded",
        "userRateLimitExceeded", "quotaExceeded", "failedPrecondition",
        "SERVICE_DISABLED", "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
    }
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, str):
            return error if error in allowed else "unknown"
        if isinstance(error, dict):
            for item in error.get("errors", []) + error.get("details", []):
                reason = item.get("reason") if isinstance(item, dict) else None
                if isinstance(reason, str) and reason in allowed:
                    return reason
    except (ValueError, TypeError):
        pass
    return "unknown"


class EmailDeliveryError(Exception):
    pass


def send_reset_code(email: str, code: str) -> None:
    client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
    sender = os.getenv("GMAIL_FROM_EMAIL", "").strip()
    if not all((client_id, client_secret, refresh_token, sender)):
        names = ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "GMAIL_FROM_EMAIL")
        missing = [name for name, value in zip(names, (client_id, client_secret, refresh_token, sender)) if not value]
        logger.error("Gmail delivery failed stage=config missing=%s", ",".join(missing))
        raise EmailDeliveryError("이메일 발송 설정이 필요합니다. Gmail API 환경변수 4개를 확인하세요.")
    stage = "message"
    try:
        message = EmailMessage()
        message["From"] = sender
        message["To"] = email
        message["Subject"] = "[moeum] 비밀번호 재설정 인증번호"
        message.set_content(f"인증번호: {code}\n10분 이내에 입력해 주세요.\n본인이 요청하지 않았다면 이 메일을 무시하세요.")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        with httpx.Client(verify=ssl.create_default_context(), timeout=10.0) as client:
            stage = "token"
            # 만료되는 access token 대신 Render에 보관한 refresh token으로 갱신합니다.
            token_response = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            access_token = token_data.get("access_token") if isinstance(token_data, dict) else None
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("Missing Gmail access token")
            stage = "send"
            response = client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or not result.get("id"):
                raise ValueError("Missing Gmail message ID")
    except httpx.HTTPStatusError as exc:
        logger.error("Gmail delivery failed stage=%s status=%s reason=%s",
                     stage, exc.response.status_code, google_error_reason(exc.response))
        raise EmailDeliveryError("인증번호 이메일을 보내지 못했습니다. 잠시 후 다시 시도하세요.") from exc
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.error("Gmail delivery failed stage=%s type=%s", stage, type(exc).__name__)
        raise EmailDeliveryError("인증번호 이메일을 보내지 못했습니다. 잠시 후 다시 시도하세요.") from exc
