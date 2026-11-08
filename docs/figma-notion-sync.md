# Figma / Notion 변경사항 수집

기존 project_activities 테이블을 사용하므로 추가 DB 테이블/마이그레이션은 필요 없습니다.
토큰은 서버 .env 또는 배포 환경 변수에만 입력합니다. API 응답/프로젝트 필드에 저장하지 않습니다.
현재 방식은 관리자 설정의 한 사용자별 서버 토큰입니다. 사용자별 OAuth 연결 UI는 포함하지 않습니다.

## 1. 인증 설정

.env.example의 다음 항목을 실제 .env에 추가하세요. 기존 DB/로그인 설정은 유지합니다.

```dotenv
FIGMA_TOKEN=발급받은_개인_액세스_토큰
FIGMA_TOKEN_OWNER_ID=프로젝트_소유자의_users_id
FIGMA_ALLOWED_FILE_KEYS=Figma_파일키
NOTION_TOKEN=발급받은_연결_토큰
NOTION_TOKEN_OWNER_ID=프로젝트_소유자의_users_id
NOTION_ALLOWED_PAGE_IDS=Notion_페이지_ID
```

OWNER_ID는 프로젝트 ID가 아니라 users.id입니다. 여러 파일/페이지 ID는 쉼표로 구분합니다.
Figma 파일키는 https://www.figma.com/design/FILE_KEY/이름 에서 FILE_KEY입니다.
Notion 페이지 ID는 페이지 링크 끝의 32자리 UUID이며 하이픈 포함/미포함 모두 허용합니다.
프로젝트 URL을 임의로 바꾸어 서버 토큰으로 다른 사용자의 자료를 읽지 못하도록 소유자와 허용 리소스를 함께 검사합니다.

- Figma 개인 액세스 토큰: file_content:read, file_versions:read 권한 필요. 해당 파일에 접근 가능한 계정에서 발급.
- Notion 내부 연결: Read content 권한을 설정하고 대상 페이지를 해당 연결과 공유하세요.
- .env 변경 후 서버를 재시작하세요. 배포 서버에도 같은 환경 변수가 필요합니다.
- 토큰을 채팅·GitHub·프론트 환경 변수에 넣지 마세요.

## 2. Swagger 순서

로그인 후 Authorize를 설정하고, 프로젝트 소유자 계정으로 실행합니다.

1. PATCH /projects/{project_id}에 figma_url 또는 notion_url 저장.
2. 인증 설정이 맞으면 응답 후 백그라운드에서 해당 서비스 최초 수집을 시도합니다.
3. GET /api/projects/{project_id}/integrations 로 linked/configured 상태 확인.
4. POST /api/projects/{project_id}/figma/sync 또는 /notion/sync 로 명시적 수집 및 결과 확인.
5. GET /api/projects/{project_id}/activities?source=figma&unorganized=true (또는 source=notion).
6. GET /api/projects/{project_id}/dashboard 의 unorganized_counts 확인.

프로젝트 생성 시 링크를 넣어도 최초 수집을 시도합니다. 이름만 수정하면 수집하지 않습니다.
이미 등록한 링크는 같은 URL을 다시 PATCH하거나 sync API를 직접 실행하면 됩니다.
최초 백그라운드 작업은 영구 작업 큐가 아니므로 서버 종료 시 유실될 수 있으며, 실패 시 로그의 상태 코드와 수동 sync 응답을 확인하세요.
프로젝트 저장 성공 자체가 외부 수집 성공을 보장하지 않습니다.
configured=true는 환경 변수 설정 검사 결과이며 토큰 유효성/외부 접근 성공 여부를 보장하지 않습니다.
주기적 스케줄러와 웹훅은 포함하지 않습니다. 이후 수정사항은 sync API를 다시 호출해야 수집됩니다.

## 3. 수집 범위

| 서비스 | 저장하는 항목 | 제한 |
| --- | --- | --- |
| Figma | 연결한 파일의 현재 버전 및 API가 제공하는 버전 기록 | 레이어별 diff/모든 편집 동작은 제공하지 않음 |
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
- 403: 서버 토큰에 허용된 프로젝트 소유자/파일/페이지가 아님
- 404: 프로젝트 소유권 또는 외부 리소스 접근 확인 필요
- 409: URL 미등록 또는 수집 중 프로젝트 연결 변경
- 422: 링크/cursor 형식 오류
- 503: 환경 변수 누락 또는 외부 요청 한도 초과 (Retry-After가 있으면 대기 후 재시도)
- 502: 외부 토큰 권한/응답/네트워크 오류
- 504: 외부 요청 시간 초과

## 공식 API 근거

- https://developers.figma.com/docs/rest-api/authentication/
- https://developers.figma.com/docs/rest-api/file-endpoints/
- https://developers.figma.com/docs/rest-api/version-history-endpoints/
- https://developers.notion.com/reference/retrieve-a-page
- https://developers.notion.com/reference/page
- https://developers.notion.com/reference/versioning

API 버전: Notion 2026-03-11. 실제 계정 수집 검증은 토큰 설정 후 진행해야 합니다.
