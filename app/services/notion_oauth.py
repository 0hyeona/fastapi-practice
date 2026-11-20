"""User-bound OAuth state and encrypted credentials; no tokens in API responses."""
import json
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.auth_session import AuthSession
from app.models.notion_account import NotionAccount
from app.models.user import User
from app.services.auth_service import hash_token, utc_now


def cipher():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise HTTPException(503, 'Notion 연결에 필요한 cryptography 패키지를 설치하세요.') from None
    try:
        return Fernet(os.environ.get('NOTION_CREDENTIAL_ENCRYPTION_KEY', '').encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'Notion 연결 암호화 키 설정이 필요합니다.') from None


def config():
    client_id = os.getenv('NOTION_CLIENT_ID', '').strip()
    secret = os.getenv('NOTION_CLIENT_SECRET', '').strip()
    redirect = os.getenv('NOTION_OAUTH_REDIRECT_URI', '').strip()
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
        raise HTTPException(503, 'NOTION_CLIENT_ID, NOTION_CLIENT_SECRET, NOTION_OAUTH_REDIRECT_URI 설정을 확인하세요.')
    return client_id, secret, redirect


def state_hash(state):
    # Different namespace from normal login tokens and GitHub login handoffs.
    return 'notion:' + hash_token(state)[:57]


def authorize(db, user_id):
    client_id, _, redirect = config()
    cipher()  # Fail before asking the user to approve an unusable connection.
    state = secrets.token_urlsafe(32)
    now = utc_now()
    db.add(AuthSession(user_id=user_id, token_hash=state_hash(state), created_at=now,
                       expires_at=now + timedelta(minutes=10)))
    db.commit()
    return {'authorization_url': 'https://api.notion.com/v1/oauth/authorize?' + urlencode({
        'client_id': client_id, 'redirect_uri': redirect, 'response_type': 'code',
        'owner': 'user', 'state': state})}


def token_request(payload):
    client_id, secret, _ = config()
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post('https://api.notion.com/v1/oauth/token',
                                   auth=(client_id, secret), json=payload,
                                   headers={'Notion-Version': '2026-03-11'})
    except httpx.RequestError:
        raise HTTPException(502, 'Notion 인증 서버에 연결할 수 없습니다. 다시 연결해 주세요.') from None
    if response.status_code != 200:
        raise HTTPException(502, 'Notion 인증에 실패했습니다. 연결 승인부터 다시 진행해 주세요.')
    try:
        data = response.json()
        if (not isinstance(data, dict) or not isinstance(data.get('access_token'), str)
                or not data['access_token'].strip()
                or ('refresh_token' in data and not isinstance(data['refresh_token'], str))):
            raise ValueError()
        return data
    except ValueError:
        raise HTTPException(502, 'Notion 인증 응답 형식이 올바르지 않습니다.') from None


def decrypt(account):
    decoder = cipher()
    # cryptography is present if cipher() succeeded.
    from cryptography.fernet import InvalidToken
    try:
        data = json.loads(decoder.decrypt(account.credentials.encode()))
        if data['user_id'] != account.user_id or not data['access_token']:
            raise ValueError()
        return data
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(503, '저장된 Notion 인증 정보를 읽을 수 없습니다. 암호화 키 설정을 확인하세요.') from None


def store(db, user_id, data):
    try:
        workspace_id = str(UUID(data['workspace_id']))
        workspace_name = data.get('workspace_name')
        if workspace_name is not None and not isinstance(workspace_name, str):
            raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, 'Notion 워크스페이스 응답이 올바르지 않습니다.') from None
    account = db.scalar(select(NotionAccount).where(NotionAccount.user_id == user_id).with_for_update())
    if account is None:
        account = NotionAccount(user_id=user_id)
        db.add(account)
    account.workspace_id = workspace_id
    account.workspace_name = workspace_name[:255] if workspace_name else None
    account.credentials = cipher().encrypt(json.dumps({
        'user_id': user_id, 'access_token': data['access_token'],
        'refresh_token': data.get('refresh_token'),
    }).encode()).decode()
    account.updated_at = utc_now()
    db.commit()
    return status(db, user_id)


def exchange(db, user_id, code, state):
    _, _, redirect = config()
    cipher()
    # Atomic consume, bound to the current authenticated user. Commit before
    # exchanging externally so a replay cannot exchange the same state twice.
    consumed = db.execute(delete(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.token_hash == state_hash(state),
        AuthSession.expires_at > utc_now()))
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, 'Notion 연결 요청이 만료되었거나 일치하지 않습니다. 다시 연결해 주세요.')
    db.commit()
    # Serialize connection replacement against refresh for this user.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    return store(db, user_id, token_request({
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect}))


def user_token(db, user_id):
    account = db.get(NotionAccount, user_id)
    return decrypt(account)['access_token'] if account is not None else None


def status(db, user_id):
    account = db.get(NotionAccount, user_id)
    return {'connected': account is not None,
            'workspace_id': account.workspace_id if account else None,
            'workspace_name': account.workspace_name if account else None}


def refresh(db, user_id):
    config()
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    account = db.scalar(select(NotionAccount).where(NotionAccount.user_id == user_id)
                        .with_for_update().execution_options(populate_existing=True))
    if account is None:
        raise HTTPException(409, '먼저 Notion 계정을 연결하세요.')
    saved = decrypt(account)
    if not saved.get('refresh_token'):
        raise HTTPException(409, 'Notion 연결 승인을 다시 진행해 주세요.')
    data = token_request({'grant_type': 'refresh_token', 'refresh_token': saved['refresh_token']})
    # A token refresh must not switch the connection to a different workspace.
    if data.get('workspace_id') != account.workspace_id:
        raise HTTPException(502, 'Notion 토큰 갱신 응답의 워크스페이스가 일치하지 않습니다.')
    return store(db, user_id, data)
