"""SMTP 설정은 .env에 저장하고 인증번호는 로그나 API 응답에 노출하지 않습니다."""

import os
import smtplib
import ssl
from email.message import EmailMessage


class EmailDeliveryError(Exception):
    pass


def send_reset_code(email: str, code: str) -> None:
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not host or not sender or not username or not password:
        raise EmailDeliveryError("이메일 발송 설정이 필요합니다.")
    message = EmailMessage()
    message["Subject"] = "[moeum] 비밀번호 재설정 인증번호"
    message["From"] = sender
    message["To"] = email
    message.set_content(f"인증번호: {code}\n10분 이내에 입력해 주세요.\n본인이 요청하지 않았다면 이 메일을 무시하세요.")
    try:
        use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
        port = int(os.getenv("SMTP_PORT", "465" if use_ssl else "587"))
        if use_ssl:
            connection = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
        else:
            connection = smtplib.SMTP(host, port, timeout=10)
        with connection as smtp:
            if not use_ssl:
                smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        raise EmailDeliveryError("인증번호 이메일을 보내지 못했습니다. 잠시 후 다시 시도하세요.") from exc
