"""SMTP 연결 및 인증만 검사합니다. 메일이나 비밀값은 출력하지 않습니다."""
import os
import smtplib
import ssl

from app.database.database import ENV_PATH  # 프로젝트 .env 로드


def main():
    stage = "configuration"
    try:
        host = os.getenv("SMTP_HOST")
        username = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")
        if not all((host, username, password, os.getenv("SMTP_FROM"))):
            print("SMTP configuration missing")
            return 1
        use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
        port = int(os.getenv("SMTP_PORT", "465" if use_ssl else "587"))
        stage = "connection"
        connection = (smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
                      if use_ssl else smtplib.SMTP(host, port, timeout=10))
        with connection as smtp:
            if not use_ssl:
                stage = "STARTTLS"
                smtp.starttls(context=ssl.create_default_context())
            stage = "authentication"
            smtp.login(username, password)
        print("SMTP connection and authentication successful. No email sent.")
        return 0
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        print(f"SMTP failed at {stage}: {type(exc).__name__}, SMTP code: {getattr(exc, 'smtp_code', 'none')}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
