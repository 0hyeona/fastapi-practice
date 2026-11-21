# 사용자별 Figma OAuth 연결

Figma 수집은 `projects.owner_id`에 해당하는 `figma_accounts`의 토큰을 사용합니다.
파일 링크는 각 프로젝트의 `projects.figma_url`에 저장합니다. 한 사용자가 여러 프로젝트에
서로 다른 파일을 등록할 수 있고, 다른 사용자는 자신의 Figma 계정으로 승인합니다.
기존 `FIGMA_TOKEN`, `FIGMA_TOKEN_OWNER_ID`, `FIGMA_ALLOWED_FILE_KEYS`는 사용하지 않습니다.
모음의 프로젝트 소유자 권한과 Figma 계정의 실제 파일 읽기 권한을 모두 충족해야 합니다.

## 1. Render와 로컬 백엔드 설정

아래 네 값을 실제 `.env`와 Render의 Environment에 설정합니다. 기존 DB 설정도 필요합니다.
사용자의 Figma 비밀번호나 파일 키를 환경변수에 넣는 방식이 아닙니다.

```dotenv
FIGMA_CLIENT_ID=Figma_OAuth_앱_Client_ID
FIGMA_CLIENT_SECRET=Figma_OAuth_앱_Client_Secret
FIGMA_REDIRECT_URI=https://프론트주소/auth/figma/callback
FIGMA_CREDENTIAL_ENCRYPTION_KEY=한_번_생성한_Fernet_키
```

암호화 키는 다음 명령으로 한 번 생성합니다. 실제 값은 Git에 올리지 않고,
재배포 후에도 같은 값을 유지합니다. 키를 바꾸면 기존 암호문을 복호화할 수 없습니다.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Figma 앱에 등록한 Redirect URL, `FIGMA_REDIRECT_URI`, 실제 프론트 콜백 주소는 일치해야 합니다.
로컬에서는 `http://localhost:5173/auth/figma/callback` 같은 주소를 사용할 수 있습니다.
Figma 앱 설정에서 `file_content:read`, `file_versions:read`를 활성화합니다.
승인 URL도 이 두 권한만 요청합니다. 현재 수집 기능은 댓글 API를 호출하지 않습니다.
댓글 수집을 추가할 때는 `file_comments:read`를 앱 설정과 요청 권한에 함께 추가하고 다시 승인받습니다.

여러 사용자에게 공개하려면 Figma 앱의 공개 범위도 확인합니다. Draft 앱은 본인과 해당 플랜 관리자만,
Private 앱은 연결된 팀/조직 사용자만 승인할 수 있습니다. 일반 외부 사용자는 승인된 Public 앱이 필요합니다.

## 2. DB 준비

서버 시작만으로 테이블이 생성되지는 않습니다. 기존 `users`, `auth_sessions`가 필요합니다.
`auth_sessions`는 승인 요청의 해시와 10분 만료 시간을 저장하는 데도 사용합니다.
원본 state는 DB에 저장하지 않으며, 일반 로그인 토큰과 다른 해시 접두사를 사용합니다.

먼저 기존 테이블을 점검합니다. 이 명령은 테이블을 변경하지 않습니다.

```bash
python -m scripts.setup_figma_accounts_db
```

`figma_accounts`가 없다면 다음 명령으로 이 테이블만 생성합니다.
또는 같은 DB에서 `sql/user_figma_accounts.sql`을 실행할 수 있습니다.

```bash
python -m scripts.setup_figma_accounts_db --apply
```

| 컬럼 | 형식 | 용도 |
| --- | --- | --- |
| `user_id` | BIGINT UNSIGNED, PK 또는 UNIQUE | `users.id`와 연결, 사용자당 한 계정 |
| `figma_user_id` | VARCHAR(128) | 승인한 Figma 계정 ID. 큰 숫자도 문자열로 보존 |
| `credentials` | TEXT | 사용자 ID와 Figma 계정 ID에 묶어 암호화한 access/refresh token |
| `expires_at` | DATETIME | access token 만료 시각, UTC |
| `updated_at` | DATETIME | 마지막 토큰 저장 시각, UTC |

기존 테이블에 이 컬럼이 있으면 새로 만들지 않습니다. 컬럼 이름이 다르거나 `user_id`의
고유 제약이 없으면 설치 스크립트가 차이를 알리고 중단합니다. `--apply`도 기존 테이블을
삭제하거나 자동 변경하지 않습니다. 기존 구조를 확인한 뒤 모델/컬럼을 맞춰야 합니다.
이미 개인 액세스 토큰을 저장했던 계정은 새 OAuth 승인으로 연결합니다.

## 3. 프론트 연결 계약

네 API 모두 모음 로그인 토큰을 `Authorization: Bearer <모음 로그인 토큰>`으로 전달합니다.
사용자 번호를 요청에 보내지 않습니다. 백엔드가 로그인 인증에서 `user.id`를 결정합니다.
Figma access/refresh token과 Client Secret은 프론트 응답에 포함하지 않습니다.

| API | 요청 본문 | 응답/역할 |
| --- | --- | --- |
| `POST /api/integrations/figma/authorize` | 없음 | `authorization_url` 반환 |
| `POST /api/integrations/figma/exchange` | `{"code":"...","state":"..."}` | 토큰 교환·암호화 저장 후 연결 상태 반환 |
| `GET /api/integrations/figma` | 없음 | 현재 로그인 사용자의 연결 상태 |
| `POST /api/integrations/figma/refresh` | 없음 | 필요할 때 수동 갱신. 보통 수집 중 자동 갱신 사용 |

프론트의 Figma 연결 버튼부터 다음 순서로 처리합니다.

1. 모음 로그인 상태에서 `authorize`를 호출합니다.
2. 응답의 `authorization_url`로 브라우저를 이동시켜 Figma 승인을 받습니다.
3. 프론트 콜백 화면에서 URL의 `code`, `state`를 읽고 로그인 토큰과 함께 `exchange`를 즉시 호출합니다.
4. 성공하면 콜백 URL에서 `code`, `state`를 제거하고 설정/프로젝트 화면으로 이동합니다.
5. 프로젝트의 Figma 파일 URL을 저장하고 기존 수집 API를 호출합니다.

Figma 승인 코드는 발급 후 30초 내 교환해야 합니다. 프론트 콜백이 준비되지 않은 상태에서
환경변수만 설정하면 계정 연결이 완료되지 않습니다. 콜백 화면의 중복 실행으로 `exchange`가
두 번 호출되지 않도록 처리합니다. 실패 후에는 새 `authorize`부터 다시 진행합니다.
기존 GitHub 로그인의 백엔드 콜백 주소와 Figma의 프론트 콜백 주소를 구분합니다.

연결 상태 응답 예시:

```json
{
  "connected": true,
  "figma_user_id": "12345678901234567890",
  "expires_at": "2027-02-19T00:00:00"
}
```

`connected`는 DB에 계정 연결이 저장되어 있다는 뜻입니다. 특정 파일의 실제 읽기 권한은
수집 시 Figma API가 확인합니다. 연결 상태 조회 자체가 파일 접근 성공을 의미하지는 않습니다.

## 4. 수집 및 갱신

프로젝트 소유자로 다음 API를 호출합니다.

```text
POST /api/projects/{project_id}/figma/sync
GET /api/projects/{project_id}/activities?source=figma&unorganized=true
GET /api/projects/{project_id}/connections
```

수집 시 DB의 사용자별 토큰을 복호화하고 `Authorization: Bearer <Figma token>`으로
파일·버전·상세 비교 요청을 보냅니다. 만료까지 60초 이하이면 자동 갱신하고 새 토큰을 저장합니다.
같은 사용자의 재승인·갱신은 사용자 DB 행 잠금으로 순차 처리하며, 잠금 후 최신 계정을 다시 읽습니다.
Figma 갱신 응답에 refresh token이 없으면 기존 refresh token을 유지합니다.
갱신 결과를 먼저 커밋하므로 이후 수집이 실패해도 새 인증 정보가 취소되지 않습니다.

Figma는 링크 저장만으로 자동 수집하지 않습니다. 수동 수집의 기본 최소 간격은 10분입니다.
버전별 중복 방지와 Story 연결 보존, 버전 간 상세 비교는 기존 수집 흐름을 사용합니다.
집계 단위는 파일 버전이며 모든 노드 수정/댓글을 각각 별도 활동으로 세는 기능은 포함하지 않습니다.

| 오류 | 확인할 내용 |
| --- | --- |
| 400 | 승인 state 만료·다른 사용자·재사용. 새 연결 승인부터 진행 |
| 401 | 모음 로그인 필요 |
| 409 | Figma 미연결, refresh token 취소·만료, 또는 기존 수집 간격/실행 중 제한 |
| 422 | 잘못된 파일 링크·cursor·요청 본문 |
| 429 | Figma 요청 한도. `Retry-After`와 기존 수집 대기 정책 확인 |
| 502/504 | Figma 인증·파일 API 응답 실패/시간 초과. 토큰·파일 접근 권한·scope 확인 |
| 503 | DB/암호화 키/앱 환경변수 설정 확인 |

## 5. 변경 파일과 검증

주요 구현: `app/models/figma_account.py`, `app/services/figma_oauth.py`,
`app/routers/figma_oauth.py`, `app/services/external_sync.py`, `app/main.py`.

```bash
python -m pytest tests/test_figma_oauth.py tests/test_external_sync.py tests/test_figma_version_diff.py tests/test_figma_sync_policy.py -q
```

테스트는 임시 SQLite와 모의 Figma 응답을 사용합니다. 실제 Figma 계정 승인, Render 배포,
운영 DB의 스키마 호환성, 프론트 콜백은 실제 환경에서 위 순서대로 확인해야 합니다.

공식 문서:

- https://developers.figma.com/docs/rest-api/oauth-apps/
- https://developers.figma.com/docs/rest-api/scopes/
