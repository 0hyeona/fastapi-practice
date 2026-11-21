# Figma / Notion 변경사항 수집

수집 결과는 기존 project_activities 테이블에 저장합니다.
Figma 인증은 사용자별 OAuth로 전환했습니다. `figma_accounts` DB 준비, 환경변수와 프론트 콜백은
[figma-user-oauth.md](figma-user-oauth.md)를 먼저 확인하세요. 토큰은 암호화 저장하며 API 응답에 포함하지 않습니다.
Notion은 사용자별 OAuth 연결을 우선 사용합니다. 설정 및 프론트 연동 계약은
[notion-user-oauth.md](notion-user-oauth.md)를 참고하세요.
아래 Notion 서버 토큰 방식은 기존 사용자 호환용입니다. 각 서비스의 OAuth 연결 UI는 프론트에서 추가해야 합니다.

## 1. 인증 설정

.env.example의 다음 항목을 실제 .env에 추가하세요. 기존 DB/로그인 설정은 유지합니다.

```dotenv
FIGMA_CLIENT_ID=Figma_OAuth_앱_Client_ID
FIGMA_CLIENT_SECRET=Figma_OAuth_앱_Client_Secret
FIGMA_REDIRECT_URI=https://프론트주소/auth/figma/callback
FIGMA_CREDENTIAL_ENCRYPTION_KEY=Fernet_암호화_키
NOTION_TOKEN=발급받은_연결_토큰
NOTION_TOKEN_OWNER_ID=프로젝트_소유자의_users_id
NOTION_ALLOWED_PAGE_IDS=Notion_페이지_ID
```

Notion 서버 토큰의 OWNER_ID는 프로젝트 ID가 아니라 users.id입니다. 여러 페이지 ID는 쉼표로 구분합니다.
Figma 파일키는 https://www.figma.com/design/FILE_KEY/이름 에서 FILE_KEY입니다.
Notion 페이지 ID는 페이지 링크 끝의 32자리 UUID이며 하이픈 포함/미포함 모두 허용합니다.
NOTION_ALLOWED_PAGE_IDS에는 Notion 페이지 URL 전체를 넣어도 페이지 ID를 추출해 검사합니다.
허용 목록에 상위 페이지를 넣어도 다른 하위 페이지까지 자동 허용하지는 않습니다.
Notion 서버 토큰은 소유자와 허용 리소스를 함께 검사합니다. Figma는 프로젝트 소유자의 OAuth 토큰과 Figma 파일 접근 권한을 사용합니다.

- Figma OAuth: file_content:read, file_versions:read 권한을 앱에 설정하고 각 사용자가 계정을 승인합니다.
- Notion 내부 연결: Read content 권한을 설정하고 대상 페이지를 해당 연결과 공유하세요.
- .env 변경 후 서버를 재시작하세요. 배포 서버에도 같은 환경 변수가 필요합니다.
- 토큰을 채팅·GitHub·프론트 환경 변수에 넣지 마세요.

## 2. Swagger 순서

로그인 후 Authorize를 설정하고, 프로젝트 소유자 계정으로 실행합니다.

1. PATCH /projects/{project_id}에 figma_url 또는 notion_url 저장.
2. Figma는 계정 연결 승인을 완료한 후 수동 수집합니다. Notion은 인증 설정이 맞으면 응답 후 백그라운드 최초 수집을 시도합니다.
3. GET /api/projects/{project_id}/integrations 로 linked/configured 상태 확인.
4. POST /api/projects/{project_id}/figma/sync 또는 /notion/sync 로 명시적 수집 및 결과 확인.
5. GET /api/projects/{project_id}/activities?source=figma&unorganized=true (또는 source=notion).
6. GET /api/projects/{project_id}/dashboard 의 unorganized_counts 확인.

Notion은 프로젝트 생성 시 링크를 넣어도 최초 수집을 시도합니다. 이름만 수정하면 수집하지 않습니다.
Figma는 기존 최소 간격 정책에 따라 sync API를 직접 실행합니다. 자세한 대기 정책은 figma-sync-policy.md를 참고하세요.
최초 백그라운드 작업은 영구 작업 큐가 아니므로 서버 종료 시 유실될 수 있으며, 실패 시 로그의 상태 코드와 수동 sync 응답을 확인하세요.
프로젝트 저장 성공 자체가 외부 수집 성공을 보장하지 않습니다.
configured=true는 사용할 인증 정보가 있다는 뜻이며 실제 파일/페이지 접근 성공 여부를 보장하지 않습니다.
주기적 스케줄러와 웹훅은 포함하지 않습니다. 이후 수정사항은 sync API를 다시 호출해야 수집됩니다.

## 3. 수집 범위

| 서비스 | 저장하는 항목 | 제한 |
| --- | --- | --- |
| Figma | 연결한 파일의 현재 버전·버전 기록, 버전 간 노드 차이 설명 | 모든 편집 동작/댓글을 각각 별도 활동으로 저장하지 않음 |
| Notion | 연결한 페이지 하나의 최근 수정 상태, 제목, 수정 시각, 링크 | 하위 페이지/데이터베이스 전체 수집 및 과거 편집 이력 복원은 포함하지 않음 |

Notion: first collection stores a baseline only; subsequent collections compare text and title. See notion-content-diff.md.
수집 사이의 여러 수정은 하나의 관측 상태로 합쳐질 수 있습니다.
Figma는 파일키와 버전 ID로 중복을 방지합니다. 현재 버전이 버전 기록에도 있으면 한 건만 저장합니다.
버전 기록 응답의 has_next=true이면 next_cursor 값을 다음 요청의 cursor에 그대로 넣습니다.
최초 수집은 첫 페이지만 처리하므로 오래된 기록이 필요하면 후속 페이지를 수동 조회하세요.
기존 활동의 Story 연결은 재동기화해도 유지됩니다. 삭제한 활동은 다시 수집될 수 있습니다.

응답 예시:

```json
{"source":"notion","fetched":1,"created":1,"existing":0,"has_next":false,"next_cursor":null}
```

## 4. 오류

- 401: 앱 로그인 필요
- 403: Notion 서버 토큰에 허용된 프로젝트 소유자/페이지가 아님
- 404: 프로젝트 소유권 또는 외부 리소스 접근 확인 필요
- 409: URL 미등록, Figma 계정 재연결 필요, 수집 간격/실행 중 제한 또는 수집 중 프로젝트 연결 변경
- 422: 링크/cursor 형식 오류
- 503: 환경 변수 누락 또는 외부 요청 한도 초과 (Retry-After가 있으면 대기 후 재시도)
- 502: 외부 토큰 권한/응답/네트워크 오류
- 504: 외부 요청 시간 초과

### Notion 설정 오류 구분

- `NOTION_TOKEN_OWNER_ID가 프로젝트 소유자와 일치하지 않습니다`: 해당 프로젝트의 `projects.owner_id`와 서버 설정을 비교하세요. 이 값은 MOEUM의 `users.id`이며 Notion 계정 ID가 아닙니다. 현재 서버 토큰은 소유자 한 명에게만 허용됩니다.
- `프로젝트의 Notion 페이지가 NOTION_ALLOWED_PAGE_IDS에 없습니다`: 프로젝트에 저장한 `notion_url`의 페이지 ID 또는 해당 URL을 허용 목록에 추가하세요. 기존 허용 페이지가 필요하면 쉼표로 추가합니다.
- `NOTION_ALLOWED_PAGE_IDS에 올바른 페이지 ID 또는 Notion 페이지 URL을 ...`: 잘못된 항목이 있으면 안전을 위해 수집을 차단합니다. 페이지 ID/URL 형식을 수정하세요.

이 검사는 Notion API 요청 전에 실행됩니다. 설정을 수정한 후 로컬 서버를 재시작하거나 Render 환경 변수 변경을 배포하고, `GET /api/projects/{project_id}/integrations`에서 Notion의 `configured`를 확인하세요. 이후 `POST /api/projects/{project_id}/notion/sync`로 실제 토큰과 페이지 공유 권한을 확인합니다.

## 공식 API 근거

- https://developers.figma.com/docs/rest-api/authentication/
- https://developers.figma.com/docs/rest-api/file-endpoints/
- https://developers.figma.com/docs/rest-api/version-history-endpoints/
- https://developers.notion.com/reference/retrieve-a-page
- https://developers.notion.com/reference/page
- https://developers.notion.com/reference/versioning

API 버전: Notion 2026-03-11. 실제 계정 수집 검증은 토큰 설정 후 진행해야 합니다.
