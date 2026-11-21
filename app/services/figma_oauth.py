"""User-bound OAuth state and encrypted, automatically refreshed Figma tokens."""
import json
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.auth_session import AuthSession
from app.models.figma_account import FigmaAccount
from app.models.user import User
from app.services.auth_service import hash_token, utc_now


SCOPES = ('file_content:read', 'file_versions:read')
REFRESH_MARGIN = timedelta(seconds=60)


def cipher():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise HTTPException(503, 'Figma 연결에 필요한 cryptography 패키지를 설치하세요.') from None
    try:
        return Fernet(os.getenv('FIGMA_CREDENTIAL_ENCRYPTION_KEY', '').strip().encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'FIGMA_CREDENTIAL_ENCRYPTION_KEY 암호화 키 설정을 확인하세요.') from None


def config():
    client_id = os.getenv('FIGMA_CLIENT_ID', '').strip()
    secret = os.getenv('FIGMA_CLIENT_SECRET', '').strip()
    redirect = os.getenv('FIGMA_REDIRECT_URI', '').strip()
    try:
        parsed = urlsplit(redirect)
        parsed.port
        valid = (parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and (parsed.scheme == 'https' or (parsed.scheme == 'http'
                      and parsed.hostname in ('localhost', '127.0.0.1'))))
    except ValueError:
        valid = False
    if not client_id or not secret or not valid:
        raise HTTPException(503, 'FIGMA_CLIENT_ID, FIGMA_CLIENT_SECRET, FIGMA_REDIRECT_URI 설정을 확인하세요.')
    return client_id, secret, redirect


def state_hash(state):
    # A Figma approval state cannot be used as a login token or Notion state.
    return 'figma:' + hash_token(state)[:58]


def authorize(db, user_id):
    client_id, _, redirect = config()
    cipher()
    state = secrets.token_urlsafe(32)
    now = utc_now()
    db.add(AuthSession(user_id=user_id, token_hash=state_hash(state), created_at=now,
                       expires_at=now + timedelta(minutes=10)))
    db.commit()
    return {'authorization_url': 'https://www.figma.com/oauth?' + urlencode({
        'client_id': client_id, 'redirect_uri': redirect, 'response_type': 'code',
        'scope': ' '.join(SCOPES), 'state': state})}


def validate_token(data):
    try:
        if (not isinstance(data, dict)
                or not isinstance(data.get('access_token'), str)
                or not data['access_token'].strip()
                or ('refresh_token' in data and (
                    not isinstance(data['refresh_token'], str) or not data['refresh_token'].strip()))
                or str(data.get('token_type', 'bearer')).lower() != 'bearer'):
            raise ValueError()
        expires = data['expires_in']
        if isinstance(expires, bool) or not isinstance(expires, (str, int)):
            raise ValueError()
        seconds = int(expires)
        if not 0 < seconds <= 315360000:
            raise ValueError()
        return seconds
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Figma 인증 응답 형식이 올바르지 않습니다.') from None


def token_request(payload, *, refresh=False):
    client_id, secret, _ = config()
    endpoint = 'refresh' if refresh else 'token'
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(f'https://api.figma.com/v1/oauth/{endpoint}',
                                   auth=(client_id, secret), data=payload,
                                   headers={'Content-Type': 'application/x-www-form-urlencoded'})
    except httpx.TimeoutException:
        raise HTTPException(504, 'Figma 인증 응답 시간이 초과되었습니다. 다시 시도해 주세요.') from None
    except httpx.RequestError:
        raise HTTPException(502, 'Figma 인증 서버에 연결할 수 없습니다.') from None
    if response.status_code == 429:
        retry = response.headers.get('retry-after', '')
        raise HTTPException(429, 'Figma 인증 요청 한도 초과. 잠시 후 다시 시도해 주세요.',
                            headers={'Retry-After': retry} if retry.isdigit() else None)
    if refresh and response.status_code in (400, 401, 403):
        raise HTTPException(409, 'Figma 인증이 만료되었거나 취소되었습니다. Figma 계정을 다시 연결해 주세요.')
    if response.status_code != 200:
        raise HTTPException(502, 'Figma 인증에 실패했습니다. 연결 승인부터 다시 진행해 주세요.')
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, 'Figma 인증 응답 형식이 올바르지 않습니다.') from None
    validate_token(data)
    return data


def decrypt(account):
    decoder = cipher()
    from cryptography.fernet import InvalidToken
    try:
        data = json.loads(decoder.decrypt(account.credentials.encode()))
        if (data['user_id'] != account.user_id
                or data['figma_user_id'] != account.figma_user_id
                or not isinstance(data['access_token'], str) or not data['access_token'].strip()
                or not isinstance(data['refresh_token'], str) or not data['refresh_token'].strip()):
            raise ValueError()
        return data
    except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, '저장된 Figma 인증 정보를 읽을 수 없습니다. 암호화 키 설정을 확인하세요.') from None


def locked_account(db, user_id):
    # Lock the user even when no connection exists yet. Reconnects and refreshes
    # share this lock because refreshing invalidates Figma's old access token.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update()
                     .execution_options(populate_existing=True))
    if user is None or user.account_status != 'active':
        raise HTTPException(409, 'Figma 연결을 저장할 사용자 계정을 확인하세요.')
    return db.scalar(select(FigmaAccount).where(FigmaAccount.user_id == user_id)
                     .with_for_update().execution_options(populate_existing=True))


def write_account(db, user_id, account, data):
    seconds = validate_token(data)
    try:
        # Keep IDs as strings: Figma IDs can exceed JavaScript's safe integers.
        identity = data.get('user_id_string', data.get('user_id'))
        if isinstance(identity, bool) or not isinstance(identity, (str, int)):
            raise ValueError()
        identity = str(identity).strip()
        refresh = data['refresh_token']
        if not identity or len(identity) > 128 or not isinstance(refresh, str) or not refresh.strip():
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Figma 계정 또는 갱신 토큰 응답이 올바르지 않습니다.') from None
    encrypted = cipher().encrypt(json.dumps({
        'user_id': user_id, 'figma_user_id': identity,
        'access_token': data['access_token'], 'refresh_token': refresh,
    }).encode()).decode()
    if account is None:
        account = FigmaAccount(user_id=user_id)
        db.add(account)
    now = utc_now()
    account.figma_user_id = identity
    account.credentials = encrypted
    account.expires_at = now + timedelta(seconds=seconds)
    account.updated_at = now
    return account


def store(db, user_id, data):
    try:
        write_account(db, user_id, locked_account(db, user_id), data)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return status(db, user_id)


def exchange(db, user_id, code, state):
    _, _, redirect = config()
    cipher()
    consumed = db.execute(delete(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.token_hash == state_hash(state),
        AuthSession.expires_at > utc_now()))
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, 'Figma 연결 요청이 만료되었거나 일치하지 않습니다. 다시 연결해 주세요.')
    # Consume before the external call so a retry cannot exchange state twice.
    db.commit()
    try:
        account = locked_account(db, user_id)
        data = token_request({'grant_type': 'authorization_code', 'code': code,
                              'redirect_uri': redirect})
        write_account(db, user_id, account, data)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return status(db, user_id)


def refresh_token(db, user_id, *, force=False):
    try:
        account = locked_account(db, user_id)
        if account is None:
            db.commit()
            return None
        credentials = decrypt(account)
        # Re-read after locking: another project/request may have refreshed it.
        if not force and account.expires_at > utc_now() + REFRESH_MARGIN:
            db.commit()
            return credentials['access_token']
        data = token_request({'refresh_token': credentials['refresh_token']}, refresh=True)
        # Figma refresh responses usually omit the reusable refresh token and ID.
        write_account(db, user_id, account, {
            **data, 'user_id_string': account.figma_user_id,
            'refresh_token': data.get('refresh_token', credentials['refresh_token']),
        })
        db.commit()
        return data['access_token']
    except Exception:
        db.rollback()
        raise


def user_token(db, user_id):
    account = db.get(FigmaAccount, user_id)
    if account is None:
        return None
    credentials = decrypt(account)
    if account.expires_at > utc_now() + REFRESH_MARGIN:
        return credentials['access_token']
    return refresh_token(db, user_id)


def status(db, user_id):
    account = db.get(FigmaAccount, user_id)
    return {'connected': account is not None,
            'figma_user_id': account.figma_user_id if account else None,
            'expires_at': account.expires_at if account else None}


def refresh(db, user_id):
    if refresh_token(db, user_id, force=True) is None:
        raise HTTPException(409, '먼저 Figma 계정을 연결하고 접근을 승인해 주세요.')
    return status(db, user_id)
