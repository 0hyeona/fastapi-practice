"""Encrypt GitHub credentials only on the backend."""
import os

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


def cipher() -> Fernet:
    try:
        return Fernet(os.environ["GITHUB_CREDENTIAL_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError) as exc:
        raise HTTPException(503, "GitHub 인증 정보 암호화 키 설정을 확인해주세요.") from exc


def decrypt_token(ciphertext: str) -> str:
    try:
        return cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(503, "GitHub 인증 정보를 읽을 수 없습니다. 서버 암호화 키를 확인해주세요.") from exc
