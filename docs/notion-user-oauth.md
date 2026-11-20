# 사용자별 Notion 연결

## 사용자 흐름

사용자가 Notion 연결 승인을 하고 읽을 페이지를 선택한 뒤 프로젝트에 그 페이지 링크를 저장합니다.
각 프로젝트는 소유자의 Notion 토큰으로만 수집합니다. OAuth로 연결한 사용자는 서버의
NOTION_TOKEN_OWNER_ID / NOTION_ALLOWED_PAGE_IDS에 추가할 필요가 없습니다.
토큰이 유효해도 사용자가 승인하지 않은 페이지는 Notion API가 차단합니다.

첫 수집은 비교 기준 본문만 저장합니다. 이후 내용/제목을 수정하고 수집하면 기존
project_notion_snapshots와 비교해 project_activities에 수정 전·후, 추가·삭제를 기록합니다.
수집 실패 시 기존 본문과 활동을 유지합니다. 현재 수집은 링크 저장 또는 수동 새로고침 때
실행합니다. 실시간 감지, 주기적 자동 수집, 웹훅은 이 변경에 포함되지 않습니다.

## 배포 전 준비

1. requirements.txt 의존성을 설치합니다 (`cryptography` 추가).
2. TiDB에서 sql/user_notion_accounts.sql을 실행하거나
   `python -m scripts.setup_notion_accounts_db --apply`를 실행합니다.
   기존 테이블/데이터는 삭제하지 않습니다. 새 테이블 없이 새 코드를 배포하지 마세요.
3. Notion Developer portal에서 다른 워크스페이스에도 설치 가능한 OAuth Integration을
   생성하고 Read content를 허용합니다. 클라이언트 ID와 Secret을 서버에 등록합니다.
4. 아래 값을 Render와 로컬 환경에 설정합니다. Secret과 키는 Git에 저장하지 않습니다.

```dotenv
NOTION_CLIENT_ID=OAuth_client_id
NOTION_CLIENT_SECRET=OAuth_client_secret
NOTION_OAUTH_REDIRECT_URI=https://프론트주소/auth/notion/callback
NOTION_CREDENTIAL_ENCRYPTION_KEY=Fernet_key
```

키 생성 명령: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
생성한 키를 비밀 환경변수로 보관하고 배포/서버 인스턴스 간 같은 키를 유지하세요.
운영 키를 바꾸려면 저장된 인증 정보의 재암호화 또는 사용자 재연결이 필요합니다.
NOTION_OAUTH_REDIRECT_URI는 Notion 설정, 프론트 콜백 경로와 정확하게 일치해야 합니다.

기존 서버 토큰 방식은 기존 소유자와 허용 페이지에 한해서만 호환됩니다.
다른 사용자에게 서버 토큰을 공유하거나 허용 목록 검사를 제거하지 않습니다.
개인 OAuth 연결이 있으면 그 토큰만 사용하며, 실패해도 서버 토큰으로 대체하지 않습니다.
현재 사용자당 워크스페이스 한 개를 연결합니다. 재연결하면 그 사용자의 기존 연결을 교체합니다.

## 프론트 연결 계약

모든 요청은 MOEUM 로그인 Bearer 토큰이 필요합니다. 브라우저 콜백을 백엔드에 직접
GET하는 방식이 아니라, 프론트 콜백이 로그인 인증을 붙여 코드를 교환하는 방식입니다.

| 순서 | API | 처리 |
| --- | --- | --- |
| 1 | POST /api/integrations/notion/authorize | authorization_url을 받아 location.assign으로 이동 |
| 2 | 프론트 /auth/notion/callback | Notion이 전달한 code/state를 읽음. error가 있으면 취소 안내 |
| 3 | POST /api/integrations/notion/exchange | JSON {"code":"...", "state":"..."} 전달 |
| 4 | 기존 PATCH /api/projects/{id}/connections/notion | {"external_url":"페이지 URL"} 저장, 최초 수집 시도 |
| 5 | POST /api/projects/{id}/notion/sync | 수정 후 수동 새로고침으로 수집 |
| 6 | GET /api/projects/{id}/activities?source=notion | 저장된 수정 기록 표시 |

exchange 성공 후 콜백 URL의 code/state를 history.replaceState로 제거하세요.
연결 상태는 GET /api/integrations/notion 으로 조회합니다.
응답은 connected/workspace_id/workspace_name만 포함하며 Notion 토큰을 프론트에 전달하지 않습니다.
연결 상태의 connected는 저장 여부이며 페이지 접근 성공을 보장하지 않습니다.
토큰 갱신은 POST /api/integrations/notion/refresh로 수행할 수 있습니다.
401/403 또는 토큰 갱신 실패 시 다시 연결 승인하도록 안내하세요.

state는 10분 유효한 일회용 값이며 생성한 MOEUM 사용자만 교환할 수 있습니다.
다른 사용자로 로그인했거나 이미 교환했으면 400을 반환합니다. 네트워크 실패 후에도 승인부터 다시 진행합니다.
인증 교환 중 기존 연결은 성공한 토큰 응답을 받은 뒤에만 교체합니다.
브라우저 콜백 페이지 구현과 Notion OAuth 앱 설정을 완료해야 실제 사용자 연결이 동작합니다.

공식 근거: https://developers.notion.com/guides/authorization/overview
