"""GitHub 인증 코드를 토큰으로 교환하고 사용자 정보를 조회합니다."""

import os
import ssl

import httpx
from fastapi import HTTPException


async def fetch_github_user(code: str) -> dict:
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    redirect_uri = os.getenv("GITHUB_REDIRECT_URI")
    if not all((client_id, client_secret, redirect_uri)):
        raise HTTPException(503, "GitHub 로그인 설정이 필요합니다.")

    try:
        # Windows의 CA/ROOT 저장소를 포함한 시스템 신뢰 인증서로 HTTPS를 검증합니다.
        async with httpx.AsyncClient(verify=ssl.create_default_context(), timeout=10.0) as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={"client_id": client_id, "client_secret": client_secret,
                      "code": code, "redirect_uri": redirect_uri},
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            if not isinstance(token_data, dict):
                raise ValueError("Invalid token response")
            if token_data.get("error") == "incorrect_client_credentials":
                raise HTTPException(503, "GitHub Client ID 또는 Client Secret이 올바르지 않습니다. 같은 OAuth App의 값으로 .env를 확인하고 서버를 재시작하세요.")
            if token_data.get("error") == "bad_verification_code":
                raise HTTPException(400, "GitHub 인증 코드가 만료되었거나 이미 사용되었습니다. 로그인부터 다시 시작하세요.")
            token = token_data.get("access_token")
            if token_data.get("error") or not isinstance(token, str) or not token:
                raise HTTPException(502, "GitHub access token을 받지 못했습니다.")
            user_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json"},
            )
            user_response.raise_for_status()
            user = user_response.json()
            if not isinstance(user, dict) or not user.get("id") or not user.get("login"):
                raise ValueError("Invalid user response")
            if type(user["id"]) is not int or user["id"] <= 0 or not isinstance(user["login"], str):
                raise ValueError("Invalid user identity")
            email_response = await client.get(
                "https://api.github.com/user/emails", params={"per_page": 100},
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json"},
            )
            email_response.raise_for_status()
            emails = email_response.json()
            if not isinstance(emails, list):
                raise ValueError("Invalid emails response")
            verified = [item for item in emails if isinstance(item, dict)
                        and item.get("verified") is True and isinstance(item.get("email"), str)]
            primary = next((item for item in verified if item.get("primary") is True), None)
            selected = primary or (verified[0] if verified else None)
            user["email"] = selected["email"] if selected else None
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "GitHub 응답 시간이 초과되었습니다. 다시 로그인하세요.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "GitHub 인증 또는 사용자 정보 조회에 실패했습니다. 다시 로그인하세요.") from exc

    # 토큰은 GitHub 요청에만 사용하고 브라우저 응답에는 포함하지 않습니다.
    return {key: user.get(key) for key in ("id", "login", "name", "email", "avatar_url", "html_url")}
