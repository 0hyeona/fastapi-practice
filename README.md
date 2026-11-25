<<<<<<< HEAD
# FastAPI Practice

## 협업자 환경 설정

실제 비밀번호는 각자의 `.env`에 저장하고, GitHub에는 `.env.example`만 공유합니다.
처음 설정할 때 아래 명령을 실행하세요. 기존 `.env`가 있으면 덮어쓰지 마세요.

```powershell
Copy-Item .env.example .env
```

- `.env`의 DB 접속 정보와 Gmail API 발송 설정을 채웁니다.
- Render 배포 시 `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_FROM_EMAIL`을 Environment에 등록하고 재배포합니다.
- 본인 Gmail 계정의 발송 권한을 한 번 허용하면 다른 회원에게 인증번호를 보낼 수 있습니다. [Gmail API 설정 안내](docs/password-reset-api.md#실제-이메일-발송-설정)를 따라 설정하세요.
- `.env`와 `tests/.env`는 Git에서 제외됩니다. 설정 후 서버를 재시작하세요.
- 현재 서버는 프로젝트 루트의 `.env`를 읽습니다. `tests/.env`는 읽지 않습니다.

## GitHub 로그인

`.env`에 같은 OAuth App의 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`,
`GITHUB_REDIRECT_URI`를 설정합니다. 로컬 callback은
`http://localhost:8000/api/auth/github/callback`입니다.

기존 DB에는 한 번 `python -m scripts.setup_github_db`를 실행하여 GitHub 회원 연결
테이블을 추가합니다. 새 DB에는 `sql/schema.sql`을 사용합니다.

기존 TiDB에는 배포 전에 `sql/github_user_oauth.sql`을 한 번 실행합니다.
Render의 `GITHUB_CREDENTIAL_ENCRYPTION_KEY`에는 아래 명령이 출력하는 값을 저장하고
이후 배포에도 같은 키를 유지합니다.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

GitHub로 로그인한 방문자는 본인 프로젝트에 공개 저장소 주소를 등록할 수 있습니다.
대시보드 조회와 동기화는 프로젝트 소유자의 OAuth 토큰을 사용합니다.
기존 방문자도 배포 후 한 번 GitHub로 다시 로그인하면 연결됩니다.
공용 전시 기기에서는 방문자마다 새 시크릿 창을 열고 체험이 끝나면 모든 시크릿 창을 닫습니다.

1. 브라우저에서 `http://localhost:8000/api/auth/github/login`을 엽니다.
2. GitHub에 로그인하고 권한에 동의합니다.
3. callback 성공 응답의 `access_token`은 **우리 서비스 로그인 토큰**이며,
   `token_type`은 `bearer`, `expires_in`은 `3600`초입니다. GitHub 토큰은 서버가 암호화하여 해당 회원의 github_accounts 행에 보관합니다.
4. Swagger의 **Authorize**에 이 토큰만 입력하면 `/api/auth/me`, 프로젝트 API,
   `/api/auth/logout`을 기존 로그인과 동일하게 사용할 수 있습니다.
****
첫 로그인은 GitHub가 인증한 이메일로 회원을 생성하며, 이후에는 변경되지 않는
GitHub 숫자 ID로 같은 회원을 찾습니다. 공개 프로필의 이메일이 비어 있어도
`/user/emails`에서 인증된 이메일을 조회합니다. 인증된 이메일이 없으면 가입할 수 없습니다.
GitHub 회원의 초기 비밀번호는 임의 값의 해시로 저장되므로 일반 비밀번호 로그인에는
사용할 수 없습니다. 기존 이메일 재설정 절차로 비밀번호를 설정할 수 있습니다.

같은 이메일로 이미 가입한 계정은 자동 연결하지 않고 `409`를 반환합니다.
이 경우 기존 계정으로 로그인해야 합니다. 비활성 계정은 `403`으로 차단합니다.
callback 주소 새로고침은 지원하지 않으며, 로그인 주소에서 다시 시작해야 합니다.

로컬에서 기존 이메일과 겹치는 GitHub 가입을 따로 테스트하려면 `.env`의
`GITHUB_TEST_EMAIL`에 고유한 `@example.com` 테스트 주소를 넣고 서버를 재시작합니다.
`localhost` 또는 `127.0.0.1` 요청에서만, 첫 가입의 이메일 중복 시 이 주소를 사용합니다.
기존 회원은 수정하지 않습니다. 임시 이메일로 이메일 발송·비밀번호 재설정은
테스트할 수 없습니다. 배포 환경에서는 이 값을 비워두세요.

## 프로젝트 CRUD API

CRUD는 생성(Create), 조회(Read), 수정(Update), 삭제(Delete)를 뜻합니다.
프로젝트 정보는 MySQL의 `projects` 테이블에 저장하며, 로그인한 회원은 본인 소유
프로젝트만 생성·조회·수정·삭제할 수 있습니다. 보관과 보관 해제도 지원합니다.

| 기능 | 메서드 및 경로 | 성공 응답 |
| --- | --- | --- |
| 생성 | `POST /projects` | `201`과 생성된 프로젝트 |
| 목록 조회 | `GET /projects` | `200`과 프로젝트 배열 |
| 상세 조회 | `GET /projects/{project_id}` | `200`과 프로젝트 |
| 부분 수정 | `PATCH /projects/{project_id}` | `200`과 수정된 프로젝트 |
| 영구 삭제 | `DELETE /projects/{project_id}` | `204`, 응답 본문 없음 |
| 보관 | `PATCH /projects/{project_id}/archive` | `200`, 상태 `archived` |
| 보관 해제 | `PATCH /projects/{project_id}/restore` | `200`, 상태 `active` |

`project_id`는 프로젝트의 숫자 `id`입니다. 회원 번호인 `owner_id`와 구분합니다.

### Swagger에서 인증하기

1. 서버 실행 후 [로컬 Swagger](http://127.0.0.1:8000/docs)를 엽니다.
   배포 서버는 [Render Swagger](https://fastapi-practice-jwse.onrender.com/docs)에서 확인합니다.
2. `POST /api/auth/login`을 열고 **Try it out**을 누릅니다. 가입한 이메일과 비밀번호로 로그인합니다.
3. 성공 응답의 `access_token` 문자열을 복사합니다. 따옴표와 쉼표는 제외합니다.
4. 페이지 위쪽 **Authorize**의 HTTPBearer Value에 토큰만 입력하고 인증합니다.
   이 입력칸에는 `Bearer` 접두어를 직접 붙이지 않습니다.
5. `projects`에서 필요한 API의 **Try it out → Execute**를 누릅니다.

토큰은 채팅이나 GitHub에 공유하지 않습니다. 수정과 조회는 같은 서버 주소에서
진행하세요. 로컬 서버와 배포 서버는 서로 다른 DB를 사용할 수 있습니다.

### 생성: POST /projects

```json
{
  "project_name": "MOEUM",
  "description": "프로젝트 변경사항을 기록하고 관리하는 서비스",
  "github_url": "https://github.com/0hyeona/fastapi-practice",
  "figma_url": null,
  "notion_url": null
}
```

이름은 필수이며 앞뒤 공백 제거 후 1~100자입니다. 설명은 선택 항목으로 최대
10,000자입니다. 세 URL은 최대 2,048자의 HTTP/HTTPS 주소를 받으며, 생략하거나
`null` 또는 빈 문자열로 보내면 `NULL`로 저장합니다.

`owner_id`는 로그인한 회원의 `users.id`를 사용하므로 생략해도 됩니다.
직접 보낸 경우 로그인한 회원 번호와 같아야 합니다. 성공하면 `201`과 프로젝트
정보가 반환되며, 응답의 `id`를 이후 조회·수정·보관·삭제에 사용합니다.
같은 요청을 다시 실행하면 새로운 프로젝트가 하나 더 생성됩니다.

### 조회: GET /projects 및 GET /projects/{project_id}

목록은 최신 프로젝트부터 반환하며 기본적으로 활성 프로젝트만 표시합니다.

| 목록 입력 항목 | 기본값 | 의미 |
| --- | --- | --- |
| `limit` | `50` | 가져올 개수, 1~100 |
| `offset` | `0` | 앞에서 건너뛸 개수, 0 이상 |
| `project_status` | `active` | `active`: 활성, `archived`: 보관, `all`: 전체 |

예를 들어 `GET /projects?limit=50&offset=0&project_status=all`은 본인의 활성·보관
프로젝트를 처음부터 최대 50개 조회합니다. 다음 페이지는 `offset=50`입니다.
`all`은 조회 옵션이며 DB에 저장하는 상태값은 아닙니다.

목록의 각 항목과 상세 응답에는 `id`, `owner_id`, `project_name`, `description`,
`github_url`, `figma_url`, `notion_url`, `project_status`, `created_at`, `updated_at`이
포함됩니다. 프론트는 URL이 있는 서비스의 아이콘을 표시할 수 있습니다.
URL 등록은 외부 서비스 계정 로그인이나 데이터 동기화를 수행하지 않습니다.

상세 조회는 `GET /projects/5`처럼 프로젝트 번호를 넣습니다. 보관된 프로젝트도
상세 조회할 수 있습니다. 목록이 `200`과 `[]`를 반환하면 조건에 맞는 본인 프로젝트가 없는 것입니다.

### 수정: PATCH /projects/{project_id}

수정할 항목만 요청 본문에 넣습니다. 아래 예시는 이름·설명을 변경하고 Figma 링크를 제거합니다.

```json
{
  "project_name": "MOEUM 수정",
  "description": "수정한 프로젝트 설명",
  "figma_url": null
}
```

보내지 않은 항목은 유지합니다. 수정 가능한 항목은 이름·설명·세 URL이며, 보관된
프로젝트도 수정할 수 있습니다. 설명과 URL은 `null`로 비울 수 있지만 이름은
`null`이나 공백으로 바꿀 수 없습니다. URL의 빈 문자열도 링크 제거로 처리합니다.
`id`, `owner_id`, `project_status`, 날짜는 이 API로 수정할 수 없습니다.

변경 내용이 있으면 `updated_at`을 갱신합니다. 성공 응답은 `200`과 수정된 정보입니다.
같은 서버의 목록이나 상세 조회에서 **Execute를 다시 눌러** 변경을 확인하세요.
Swagger의 이전 조회 결과는 자동으로 새로고침되지 않습니다.

### 보관 및 보관 해제

`PATCH /projects/5/archive`는 상태를 `archived`로 바꿉니다. DB 행, 이름, 설명과 URL은
유지되며 기본 목록에서는 빠집니다. `GET /projects?project_status=archived`로 확인합니다.

`PATCH /projects/5/restore`는 상태를 `active`로 바꾸며 기본 목록에 다시 표시됩니다.
두 API 모두 요청 본문은 없습니다. 이미 같은 상태라면 변경 없이 `200`을 반환합니다.

### 삭제: DELETE /projects/{project_id}

`DELETE /projects/5`는 해당 프로젝트를 DB에서 **영구 삭제**합니다. 보관과 달리
복원할 수 없으므로 삭제 확인 화면은 프론트에서 제공하고, Swagger 테스트에는
테스트용 프로젝트를 사용하세요. 요청 본문은 없습니다.

성공 시 `204`이고 응답 본문이 비어 있는 것이 정상입니다. 삭제 후 목록을 다시
조회하면 제외되고, 같은 프로젝트 상세 조회 또는 재삭제는 `404`를 반환합니다.

### 오류 응답과 테스트 순서

| 코드 | 의미 |
| --- | --- |
| `401` | 토큰 없음·만료·유효하지 않음: 다시 로그인하고 Authorize에 입력 |
| `403` | 생성 요청의 `owner_id`가 로그인한 회원과 다름 |
| `404` | 프로젝트가 없거나 다른 회원 소유임 |
| `422` | 입력 형식 오류: 이름·URL·프로젝트 번호·페이지 옵션 등 확인 |

테스트는 **생성 → 목록·상세 조회 → 수정 → 재조회 → 보관 → 보관 목록 조회 →
보관 해제 → 삭제 → 재조회** 순서로 진행합니다. 생성한 `id`를 계속 사용하고,
각 단계의 Server response 코드와 실제 응답을 확인합니다.

새 DB는 `sql/schema.sql`로 준비합니다. 기존 DB에 URL 컬럼이 없다면
`sql/migrate_project_urls.sql`을 한 번 실행합니다. 이미 컬럼이 있으면 다시 실행하지
마세요. 배포 환경의 DB에도 동일한 컬럼이 필요합니다.
자동 검증은 `python -m unittest discover -s tests -v`로 실행할 수 있습니다.
추가 설명은 [프로젝트 API 안내](docs/project-api.md)를 참고하세요.

## 비밀번호 찾기

이메일 확인 → 6자리 인증번호 발송·확인 → 새 비밀번호 설정 API를 제공합니다.
요청 형식, 화면 연결 순서, Gmail API 설정은 [비밀번호 찾기 API 안내](docs/password-reset-api.md)를 참고하세요.

## 로그인 API

회원가입과 로그인은 같은 MySQL `users` 테이블을 사용합니다. 로그인 세션은
`auth_sessions`에 저장합니다. 기존 DB에는 `sql/schema.sql`을 다시 실행하여
세션 테이블을 추가할 수 있습니다. 기존 회원 데이터는 유지됩니다.

기존 `users`에 `name` 컬럼이 없다면 아래 명령으로 컬럼과 세션 테이블을
준비합니다. 기존 회원의 초기 이름에는 아이디를 사용합니다.

```bash
python -m scripts.setup_login_db
```

`POST /api/auth/login`에 다음 JSON을 전송합니다. 회원가입 때 사용한 이메일과
비밀번호를 입력하세요.

```json
{
  "email": "testuser@example.com",
  "password": "test-password-123"
}
```

성공하면 `200`과 `access_token`, `token_type`, `expires_in`(3600초), `user`가
반환됩니다. 비밀번호 오류, 등록되지 않은 이메일, 비활성 계정은 동일한 `401` 응답을
반환하며 잘못된 입력 형식은 `422`입니다.

반환된 토큰을 아래 헤더에 넣어 요청합니다.

```text
Authorization: Bearer <access_token>
```

- `GET /api/auth/me`: 로그인한 회원 정보 조회
- `POST /api/auth/logout`: 현재 세션 삭제, 성공 시 `204`

Swagger `/docs`에서 로그인 후 **Authorize** 버튼에 토큰을 입력하여 테스트할
수 있습니다. 토큰은 1시간 뒤 만료되고 로그아웃한 토큰은 즉시 사용할 수 없습니다.
DB에는 원본 토큰 대신 SHA-256 해시를 저장하고 날짜는 UTC로 저장합니다.
여러 번 로그인하면 각각 독립된 세션이 생성됩니다.

인증 구현 참고: [FastAPI 공식 보안 문서](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
이 프로젝트는 JWT 대신 DB에서 확인하고 삭제할 수 있는 세션 토큰을 사용합니다.

FastAPI를 이용한 백엔드 API 연습 및 협업용 프로젝트입니다.

## 개발 환경

- Python 3.x
- FastAPI
- Uvicorn
- IntelliJ IDEA

## 폴더 구조

```text
fastapi-practice/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ routers/
│  │  ├─ __init__.py
│  │  └─ projects.py
│  ├─ schemas/
│  │  ├─ __init__.py
│  │  └─ project.py
│  ├─ services/
│  │  └─ __init__.py
│  └─ models/
│     └─ __init__.py
├─ requirements.txt
├─ README.md
└─ .gitignore
```

### 각 폴더의 의미와 역할

상위 폴더는 그 아래에 있는 파일과 폴더를 묶는 공간입니다. 예를 들어
`app/routers/projects.py`에서 `app`은 `routers`의 상위 폴더이고,
`routers`는 `projects.py`가 들어 있는 폴더입니다.

| 폴더 | 상위 폴더 | 의미와 역할 |
| --- | --- | --- |
| `fastapi-practice/` | 프로젝트를 보관한 외부 폴더 | 프로젝트의 최상위 폴더(루트)입니다. 애플리케이션 코드와 실행·설정·안내 파일을 모두 포함합니다. 터미널에서 서버 실행 명령을 입력하는 기준 위치입니다. |
| `app/` | `fastapi-practice/` | 실제 FastAPI 애플리케이션 코드를 모으는 폴더입니다. `main.py`에서 앱을 생성하고 각 기능의 라우터를 등록합니다. |
| `app/routers/` | `app/` | 클라이언트의 요청을 받는 API 경로와 처리 함수를 모으는 폴더입니다. `projects.py`에는 프로젝트 관련 API를 작성합니다. |
| `app/schemas/` | `app/` | API 요청과 응답의 데이터 형식을 정의하는 폴더입니다. Pydantic 모델로 필드와 유효성 검사 규칙을 작성하며, `project.py`에는 프로젝트 관련 스키마를 정의합니다. |
| `app/services/` | `app/` | 요청 처리에 필요한 비즈니스 로직을 모으는 폴더입니다. 프로젝트 처리나 GitHub·Figma·Notion 같은 외부 서비스 연동 로직을 작성합니다. |
| `app/models/` | `app/` | 데이터베이스에 저장할 데이터의 구조를 정의하는 폴더입니다. 데이터베이스 연동 시 테이블과 연결되는 모델을 작성합니다. |

각 폴더의 `__init__.py`는 해당 폴더를 Python 패키지로 인식하게 하는 파일입니다.
이를 통해 `from app.routers import projects`처럼 다른 모듈에서 코드를 가져올 수 있습니다.

루트에 있는 `requirements.txt`는 설치할 Python 패키지 목록,
`README.md`는 프로젝트 안내 문서, `.gitignore`는 Git에서 제외할 파일과 폴더의 규칙을 담습니다.

현재 회원가입·로그인·로그아웃·비밀번호 재설정과 프로젝트 CRUD·보관 API가 구현되어 있습니다.
API는 `.env`로 설정한 MySQL을 사용하며, 서버 실행 시 테이블을 자동 생성하지 않습니다.
기존 `pyproject.toml`과 `uv.lock`은 프로젝트 루트에 유지합니다.

## 실행 방법

### 1. 프로젝트 Clone

```bash
git clone https://github.com/0hyeona/fastapi-practice.git
```

프로젝트 폴더로 이동합니다.

```bash
cd fastapi-practice
```

### 2. 가상환경 생성

```bash
python -m venv .venv
```

### 3. 가상환경 활성화

Windows

```bash
.venv\Scripts\activate
```

Mac / Linux

```bash
source .venv/bin/activate
```

가상환경이 활성화되면 터미널 앞에 아래와 같이 표시됩니다.

```text
(.venv)
```

### 4. 패키지 설치

```bash
pip install -r requirements.txt
```

### 5. MySQL 설정

MySQL에서 `sql/schema.sql`을 실행하여 `moeum` 데이터베이스와 `users` 테이블을
준비합니다. 이미 있는 테이블은 이 파일로 변경되지 않습니다.

프로젝트 루트의 `.env.example`을 `.env`라는 이름으로 복사하고,
본인의 MySQL 접속 정보로 수정합니다. Windows 터미널에서는 다음을 실행합니다.

```powershell
Copy-Item .env.example .env
```

이미 `.env`가 있으면 복사하지 말고 기존 설정을 사용합니다.
`.env`의 실제 비밀번호는 GitHub에 올리지 않습니다.

### 6. FastAPI 서버 실행

```bash
fastapi dev app/main.py
```

명령어가 동작하지 않는 경우 아래 명령어를 사용합니다.

```bash
python -m uvicorn app.main:app --reload
```

### 7. 서버 확인

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000
```

### 8. Swagger API 문서 확인

FastAPI에서 자동으로 생성되는 Swagger 문서는 아래 주소에서 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

Swagger에서 현재 구현된 API를 확인하고 직접 테스트할 수 있습니다.

## 회원가입 테스트

서버 실행 후 `http://127.0.0.1:8000/docs`에서 `POST /api/auth/signup`을 열고
**Try it out**을 눌러 다음 JSON을 입력합니다.

```json
{
  "user_id": "testuser",
  "name": "테스트 회원",
  "email": "testuser@example.com",
  "password": "test-password-123"
}
```

아이디와 이름은 앞뒤 공백을 제거한 뒤 1~50자, 비밀번호는 8~128자여야 합니다.
이메일은 올바른 이메일 형식이어야 합니다. 성공 시 `201`, 아이디 또는 이메일
중복 시 `409`, 입력 형식 오류 시 `422`를 반환합니다. 비밀번호는 Argon2로 해싱해
저장하고 응답에는 비밀번호와 해시값을 포함하지 않습니다.

회원가입 관련 파일:

- `app/models/user.py`: 기존 users 테이블 매핑
- `app/schemas/auth.py`: 요청 검사 및 응답 형식
- `app/services/auth_service.py`: 중복 확인, 해싱, 저장
- `app/routers/auth.py`: 회원가입 API

자동 검증은 실제 MySQL 대신 임시 DB를 사용합니다.

```bash
python -m unittest discover -s tests -v
```

## 서버 종료

서버가 실행 중인 터미널에서 아래 단축키를 입력합니다.

```text
Ctrl + C
```

## 가상환경 종료

```bash
deactivate
```

## 패키지 추가 시

새로운 패키지를 설치한 경우 `requirements.txt`를 업데이트합니다.

```bash
pip freeze > requirements.txt
```

## Git 사용 시 참고

`.venv`, `.idea`, `.env` 등 개인 개발 환경 파일은 GitHub에 업로드하지 않습니다.

`.gitignore` 예시:

```gitignore
.venv/
.idea/
__pycache__/
.env
*.pyc
*.iml
```


## Story / Project Activities API

Story 작성·관리와 GitHub/Figma/Notion 변경사항 등록·관리 API: [사용 문서](docs/story-activity-api.md).
기존 DB에는 `sql/migrate_stories_activities.sql`을 먼저 적용합니다.

### GitHub dashboard

DB 테이블, IntelliJ 연결, 신규 API 실행 방법: [GitHub dashboard guide](docs/github-dashboard-api.md).

### Figma / Notion integrations

변경사항 수집, 인증 설정 및 Swagger 사용법: [연동 안내](docs/figma-notion-sync.md).

- Figma 사용자별 OAuth 연결·Render 환경변수·DB 준비·프론트 콜백: [figma-user-oauth.md](docs/figma-user-oauth.md)

- 수집 실행 이력 및 DB 추가 방법: [project-sync-runs.md](docs/project-sync-runs.md)
- Notion 수집 시점, 문장 수정 전후 비교 및 기록 제외 기준은 아래 **Notion 변경사항 수집 기준**을 참고하세요.

## Notion 변경사항 수집 기준

Notion의 연결된 페이지를 읽는 **수집 실행**과, 이전에 저장한 내용과 달라진 부분을
`project_activities`에 남기는 **변경 기록 생성**은 별개입니다.
새로고침에 성공해도 달라진 본문이 없으면 새 기록은 0개입니다.

### 1. 언제 수집을 실행하나요?

| 상황 | Notion API 수집 실행 | 동작 |
| --- | --- | --- |
| Notion URL을 넣어 프로젝트 생성 | 설정이 맞으면 백그라운드에서 시도 | 최초 비교 기준을 저장합니다. 프로젝트 저장 성공이 수집 성공을 보장하지는 않습니다. |
| 프로젝트의 Notion URL 저장·교체 | 설정이 맞으면 백그라운드에서 시도 | 같은 URL을 다시 저장해도 시도할 수 있습니다. 다른 페이지는 별도 비교 기준을 사용합니다. |
| 현재 프론트에서 활성 프로젝트를 처음 불러옴 | URL이 있으면 시도 | `ProjectsContext`가 Notion 수집 후 저장된 목록을 조회합니다. 프로젝트 또는 Notion URL 변경도 실행 조건입니다. |
| MOEUM의 Notion 새로고침 버튼 클릭 | 실행 | 수집 API를 호출한 뒤 저장된 변경사항 목록을 다시 조회합니다. |
| 브라우저 전체 새로고침으로 프론트가 다시 마운트됨 | 활성 프로젝트와 URL이 준비되면 시도 | Notion 페이지를 수정하지 않았다면 새 기록은 생기지 않습니다. |
| `POST /api/projects/{project_id}/notion/sync` 직접 호출 | 실행 | 로그인과 프로젝트 접근 권한, 페이지 접근 설정을 검사합니다. |
| `GET /api/projects/{project_id}/activities?source=notion` | 실행하지 않음 | 이미 DB에 저장된 기록만 조회합니다. 대시보드·연결 상태의 GET API도 수집 명령이 아닙니다. |
| 프로젝트 이름·설명만 변경 | 해당 저장 요청에서는 실행하지 않음 | Notion URL 저장과 구분합니다. |
| 같은 프로젝트에서 화면만 이동 | 이것만으로 실행하지 않음 | 프론트가 재마운트되거나 수집 효과의 의존 값이 바뀌는 경우는 위 조건을 따릅니다. |
| Notion에서 편집만 하고 MOEUM을 사용하지 않음 | 실행하지 않음 | 현재 주기적 수집 스케줄러·Notion 변경 웹훅은 없습니다. |
| Notion 계정 승인·연결만 완료 | 계정 연결 API 자체에서는 실행하지 않음 | 페이지 URL 저장 또는 수동 새로고침으로 수집을 실행하세요. |

Notion URL이 없거나, 프로젝트 소유자의 Notion 연결·호환 서버 토큰 설정이 맞지 않으면
수집을 진행할 수 없습니다. OAuth 연결에서는 해당 연결이 접근할 수 있는 페이지여야 합니다.
서버 토큰 방식은 `NOTION_TOKEN`, `NOTION_TOKEN_OWNER_ID`, `NOTION_ALLOWED_PAGE_IDS`도 검사합니다.
URL을 아는 것만으로 비공개 페이지의 읽기 권한이 생기지는 않습니다.

### 2. 언제 변경 기록을 만드나요?

첫 수집은 페이지 제목과 블록별 본문을 `project_notion_snapshots`에 저장합니다.
비교할 이전 내용이 없으므로 기존 문서를 전부 '추가된 내용'으로 기록하지 않습니다.
두 번째 수집부터 저장된 기준과 새로 읽은 내용을 비교합니다.

| 수집 전후의 차이 | 생성되는 기록 | 화면에 표시할 내용 |
| --- | --- | --- |
| 같은 블록의 기존 문장을 다른 문장으로 수정 | `content_updated` · 내용 수정 | `수정 전`과 `수정 후`의 실제 문장 |
| 새 블록에 본문을 작성하거나 기존 빈 문단에 글을 입력 | `content_added` · 내용 추가 | `추가된 내용` |
| 본문이 있는 블록을 삭제하거나 기존 문장을 모두 지움 | `content_deleted` · 내용 삭제 | `삭제된 내용`에 이전 문장 보존 |
| 페이지 제목 수정 | `title_changed` · 제목 변경 | 이전 제목과 변경한 제목 |
| 본문이 있는 체크박스의 체크 상태 변경 | `content_updated` · 내용 수정 | `[ ] 할 일` → `[x] 할 일`처럼 전후 내용 |
| 이미지·파일·동영상 등 요소 추가·삭제 | 내용 추가 또는 삭제 | `[이미지]`, `[파일]` 등 요소 종류와 제공된 캡션. 이미지 내부 픽셀·문자를 자동 분석하는 기능은 아닙니다. |
| 수식 또는 표 셀의 본문 변경 | 내용 수정 등 | API에서 읽은 수식 표현식 또는 셀 텍스트의 차이 |

문장 비교는 **블록 ID**를 기준으로 합니다. 기존 문단의 글자를 고치면 수정 전후로 비교하지만,
문단 자체를 삭제하고 새 문단을 만들면 서로 다른 블록이므로 삭제와 추가로 나뉠 수 있습니다.
기존 문장이 없는 추가 기록에 임의의 '수정 전 문장'을 만들지는 않습니다.

### 3. 언제 새 기록을 만들지 않나요?

| 상황 | 처리 |
| --- | --- |
| 최초 수집 또는 처음 연결한 다른 페이지 | 기준만 저장하고 변경 기록은 만들지 않습니다. |
| 저장한 제목·비교 대상 본문과 동일 | 중복 기록을 만들지 않습니다. |
| 엔터로 만든 빈 문단, 공백만 있는 블록의 추가·삭제 | 본문 변경 기록에서 제외합니다. |
| 본문이 없는 체크박스의 추가 또는 체크만 변경 | 빈 문장 변경으로 기록하지 않습니다. |
| 모든 셀이 빈 표 행의 추가·삭제 | 빈 본문 기록을 만들지 않습니다. |
| 단·표·동기화 블록 같은 구조 컨테이너 자체의 추가 | 컨테이너만으로 본문 기록을 만들지 않습니다. 읽을 수 있는 하위 블록의 본문은 따로 비교합니다. |
| 글꼴·색상·굵기·블록 종류·배치만 바뀌고 비교 본문은 동일 | 현재 문장 비교 범위에서는 새 기록을 만들지 않습니다. |
| API가 지원하지 않는 블록 | 내용을 임의로 추정하지 않습니다. 이미 같은 ID로 저장된 본문은 보존합니다. 처음부터 읽을 수 없던 본문은 비교 기준으로 확정하지 않습니다. |

빈 블록·구조만 달라진 경우에도 정상 수집한 현재 상태는 다음 비교 기준으로 저장합니다.
본문 변경이 없다는 사실과 수집 실패를 구분합니다.

### 4. 수정 전후 비교 예시와 확인 순서

1. Notion 페이지 URL과 읽기 권한을 연결합니다.
2. MOEUM에서 **Notion 새로고침**을 눌러 현재 본문을 기준으로 저장합니다.
3. Notion에서 **기존 문단의 문장**을 수정합니다.
4. MOEUM에서 **Notion 새로고침**을 다시 누릅니다.
5. 변경사항 카드에서 다음과 같이 실제 문장이 구분되는지 확인합니다.

```text
수정 전: 전시회 날짜는 11월 20일입니다.
수정 후: 전시회 날짜는 11월 21일입니다.
```

수집 사이에 문장을 여러 번 수정했다면 마지막으로 수집한 문장과 이번에 수집한 문장만 비교합니다.
예를 들어 수집 전에 A → B → C로 수정했다면 A → C만 기록할 수 있으며,
A → B → A로 돌아오면 관측된 차이가 없어 기록이 생기지 않을 수 있습니다.
Notion의 전체 과거 버전 이력이나 모든 키 입력을 복원하는 기능은 아닙니다.

### 5. 수집 실패·본문 누락·페이지 교체 시 처리

- 권한 오류, 토큰 오류, 요청 한도, 시간 초과, 잘못된 응답, 하위 블록 조회 실패 시
  부분 수집 내용을 성공한 비교 기준으로 저장하지 않습니다. 기존 본문과 활동 기록을 유지합니다.
- 문단 등 텍스트 블록에서 필수 텍스트 필드가 빠지면 '빈 문장'으로 간주하지 않고 수집 실패로 처리합니다.
- 수집 시작과 끝의 페이지 제목·수정 시각이 다르면 수집 도중 바뀐 것으로 보고 저장하지 않습니다.
  편집이 끝난 뒤 새로고침하세요.
- 같은 프로젝트의 Notion 수집은 프로젝트 DB 잠금으로 순차 처리합니다.
- 시도 결과는 `project_sync_runs`에 남습니다. `GET /api/projects/{project_id}/sync-runs`로 확인할 수 있습니다.
- 페이지 URL을 바꾸면 새 페이지 ID의 별도 기준을 사용합니다. 이전 페이지 기록은 DB에 유지하지만,
  현재 연결한 페이지 기준의 Notion 활동 조회에서는 제외합니다. 하위 페이지를 자동으로 같은 페이지로 취급하지 않습니다.
- 이미 본문 없이 저장된 옛 기록은 이번 수정으로 과거 문장을 복원할 수 없습니다.
  화면의 '텍스트가 없는 블록이거나 상세 내용이 제공되지 않았어요'는 과거 기록에 표시할 본문이 없을 때의
  프론트 안내 문구이며, Notion이 직접 반환한 오류 메시지가 아닙니다.

### 6. 수집 범위와 DB/API

연결된 페이지 하나의 제목과 읽을 수 있는 하위 블록을 수집합니다.
하위 블록 목록은 페이지 끝까지 조회하고, 중첩 블록도 순회합니다.
별도 하위 페이지와 하위 데이터베이스의 내부 항목 전체는 순회하지 않으며 제목만 다룹니다.
파일 바이너리, 이미지 픽셀, 동영상 내용, 페이지 전체의 시각적 배치는 비교하지 않습니다.
안전상 중첩 깊이 50 초과 또는 블록 목록 요청 200회 초과 시 부분 결과를 저장하지 않고 실패 처리합니다.

| 저장 위치 / API | 역할 |
| --- | --- |
| `projects.notion_url` | 현재 연결한 페이지 URL |
| `project_notion_snapshots` | 프로젝트·페이지 ID별 마지막 정상 수집 본문과 비교 기준 |
| `project_activities` | 본문·제목 차이에서 생성한 변경 기록 |
| `project_sync_runs` | 수집 실행 성공·실패 이력 |
| `POST /api/projects/{project_id}/notion/sync` | 실제 수집 및 비교 실행 |
| `GET /api/projects/{project_id}/activities?source=notion&unorganized=true` | 현재 페이지의 미정리 기록 조회 |
| `GET /api/projects/{project_id}/integrations` | 연결 설정 상태 확인. 실제 페이지 읽기 성공을 보장하는 검사는 아닙니다. |

응답의 `fetched`와 `created`는 이 Notion 비교 흐름에서 생성한 변경 기록 수입니다.
읽은 전체 블록 수나 Notion API 호출 횟수가 아닙니다. 첫 기준 저장·변경 없음은 두 값 모두 0일 수 있습니다.

이 기능에는 위 테이블이 필요합니다. 서버 실행만으로 테이블을 자동 생성하지 않으므로
기존 설치는 [Notion 본문 비교 안내](docs/notion-content-diff.md)와
[수집 이력 안내](docs/project-sync-runs.md)의 스키마 준비 내용을 확인하세요.
이번 빈 본문·문장 비교 수정에는 추가 테이블이나 새 컬럼이 필요하지 않습니다.

구현: `app/services/notion_content.py`, `app/services/external_sync.py`,
`app/services/initial_sync.py`, `app/routers/project_integrations.py`.
프론트 실행 조건은 `moeum` 저장소의 `src/state/ProjectsContext.tsx`와
`src/api/externalActivities.ts`를 기준으로 합니다.

관련 검증은 임시 SQLite와 모의 API 응답으로 실행하며 실제 Notion 문서를 수정하지 않습니다.

```bash
python -m pytest tests/test_notion_content.py tests/test_external_sync.py tests/test_current_notion_page.py -q
```
=======
# FastAPI Practice

## 협업자 환경 설정

실제 비밀번호는 각자의 `.env`에 저장하고, GitHub에는 `.env.example`만 공유합니다.
처음 설정할 때 아래 명령을 실행하세요. 기존 `.env`가 있으면 덮어쓰지 마세요.

```powershell
Copy-Item .env.example .env
```

- `.env`의 DB 접속 정보와 Gmail API 발송 설정을 채웁니다.
- Render 배포 시 `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_FROM_EMAIL`을 Environment에 등록하고 재배포합니다.
- 본인 Gmail 계정의 발송 권한을 한 번 허용하면 다른 회원에게 인증번호를 보낼 수 있습니다. [Gmail API 설정 안내](docs/password-reset-api.md#실제-이메일-발송-설정)를 따라 설정하세요.
- `.env`와 `tests/.env`는 Git에서 제외됩니다. 설정 후 서버를 재시작하세요.
- 현재 서버는 프로젝트 루트의 `.env`를 읽습니다. `tests/.env`는 읽지 않습니다.

## GitHub 로그인

`.env`에 같은 OAuth App의 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`,
`GITHUB_REDIRECT_URI`를 설정합니다. 로컬 callback은
`http://localhost:8000/api/auth/github/callback`입니다.

기존 DB에는 한 번 `python -m scripts.setup_github_db`를 실행하여 GitHub 회원 연결
테이블을 추가합니다. 새 DB에는 `sql/schema.sql`을 사용합니다.

기존 TiDB에는 배포 전에 `sql/github_user_oauth.sql`을 한 번 실행합니다.
Render의 `GITHUB_CREDENTIAL_ENCRYPTION_KEY`에는 아래 명령이 출력하는 값을 저장하고
이후 배포에도 같은 키를 유지합니다.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

GitHub로 로그인한 방문자는 본인 프로젝트에 공개 저장소 주소를 등록할 수 있습니다.
대시보드 조회와 동기화는 프로젝트 소유자의 OAuth 토큰을 사용합니다.
기존 방문자도 배포 후 한 번 GitHub로 다시 로그인하면 연결됩니다.
공용 전시 기기에서는 방문자마다 새 시크릿 창을 열고 체험이 끝나면 모든 시크릿 창을 닫습니다.

1. 브라우저에서 `http://localhost:8000/api/auth/github/login`을 엽니다.
2. GitHub에 로그인하고 권한에 동의합니다.
3. callback 성공 응답의 `access_token`은 **우리 서비스 로그인 토큰**이며,
   `token_type`은 `bearer`, `expires_in`은 `3600`초입니다. GitHub 토큰은 서버가 암호화하여 해당 회원의 github_accounts 행에 보관합니다.
4. Swagger의 **Authorize**에 이 토큰만 입력하면 `/api/auth/me`, 프로젝트 API,
   `/api/auth/logout`을 기존 로그인과 동일하게 사용할 수 있습니다.
****
첫 로그인은 GitHub가 인증한 이메일로 회원을 생성하며, 이후에는 변경되지 않는
GitHub 숫자 ID로 같은 회원을 찾습니다. 공개 프로필의 이메일이 비어 있어도
`/user/emails`에서 인증된 이메일을 조회합니다. 인증된 이메일이 없으면 가입할 수 없습니다.
GitHub 회원의 초기 비밀번호는 임의 값의 해시로 저장되므로 일반 비밀번호 로그인에는
사용할 수 없습니다. 기존 이메일 재설정 절차로 비밀번호를 설정할 수 있습니다.

같은 이메일로 이미 가입한 계정은 자동 연결하지 않고 `409`를 반환합니다.
이 경우 기존 계정으로 로그인해야 합니다. 비활성 계정은 `403`으로 차단합니다.
callback 주소 새로고침은 지원하지 않으며, 로그인 주소에서 다시 시작해야 합니다.

로컬에서 기존 이메일과 겹치는 GitHub 가입을 따로 테스트하려면 `.env`의
`GITHUB_TEST_EMAIL`에 고유한 `@example.com` 테스트 주소를 넣고 서버를 재시작합니다.
`localhost` 또는 `127.0.0.1` 요청에서만, 첫 가입의 이메일 중복 시 이 주소를 사용합니다.
기존 회원은 수정하지 않습니다. 임시 이메일로 이메일 발송·비밀번호 재설정은
테스트할 수 없습니다. 배포 환경에서는 이 값을 비워두세요.

## 프로젝트 CRUD API

CRUD는 생성(Create), 조회(Read), 수정(Update), 삭제(Delete)를 뜻합니다.
프로젝트 정보는 MySQL의 `projects` 테이블에 저장하며, 로그인한 회원은 본인 소유
프로젝트만 생성·조회·수정·삭제할 수 있습니다. 보관과 보관 해제도 지원합니다.

| 기능 | 메서드 및 경로 | 성공 응답 |
| --- | --- | --- |
| 생성 | `POST /projects` | `201`과 생성된 프로젝트 |
| 목록 조회 | `GET /projects` | `200`과 프로젝트 배열 |
| 상세 조회 | `GET /projects/{project_id}` | `200`과 프로젝트 |
| 부분 수정 | `PATCH /projects/{project_id}` | `200`과 수정된 프로젝트 |
| 영구 삭제 | `DELETE /projects/{project_id}` | `204`, 응답 본문 없음 |
| 보관 | `PATCH /projects/{project_id}/archive` | `200`, 상태 `archived` |
| 보관 해제 | `PATCH /projects/{project_id}/restore` | `200`, 상태 `active` |

`project_id`는 프로젝트의 숫자 `id`입니다. 회원 번호인 `owner_id`와 구분합니다.

### Swagger에서 인증하기

1. 서버 실행 후 [로컬 Swagger](http://127.0.0.1:8000/docs)를 엽니다.
   배포 서버는 [Render Swagger](https://fastapi-practice-jwse.onrender.com/docs)에서 확인합니다.
2. `POST /api/auth/login`을 열고 **Try it out**을 누릅니다. 가입한 이메일과 비밀번호로 로그인합니다.
3. 성공 응답의 `access_token` 문자열을 복사합니다. 따옴표와 쉼표는 제외합니다.
4. 페이지 위쪽 **Authorize**의 HTTPBearer Value에 토큰만 입력하고 인증합니다.
   이 입력칸에는 `Bearer` 접두어를 직접 붙이지 않습니다.
5. `projects`에서 필요한 API의 **Try it out → Execute**를 누릅니다.

토큰은 채팅이나 GitHub에 공유하지 않습니다. 수정과 조회는 같은 서버 주소에서
진행하세요. 로컬 서버와 배포 서버는 서로 다른 DB를 사용할 수 있습니다.

### 생성: POST /projects

```json
{
  "project_name": "MOEUM",
  "description": "프로젝트 변경사항을 기록하고 관리하는 서비스",
  "github_url": "https://github.com/0hyeona/fastapi-practice",
  "figma_url": null,
  "notion_url": null
}
```

이름은 필수이며 앞뒤 공백 제거 후 1~100자입니다. 설명은 선택 항목으로 최대
10,000자입니다. 세 URL은 최대 2,048자의 HTTP/HTTPS 주소를 받으며, 생략하거나
`null` 또는 빈 문자열로 보내면 `NULL`로 저장합니다.

`owner_id`는 로그인한 회원의 `users.id`를 사용하므로 생략해도 됩니다.
직접 보낸 경우 로그인한 회원 번호와 같아야 합니다. 성공하면 `201`과 프로젝트
정보가 반환되며, 응답의 `id`를 이후 조회·수정·보관·삭제에 사용합니다.
같은 요청을 다시 실행하면 새로운 프로젝트가 하나 더 생성됩니다.

### 조회: GET /projects 및 GET /projects/{project_id}

목록은 최신 프로젝트부터 반환하며 기본적으로 활성 프로젝트만 표시합니다.

| 목록 입력 항목 | 기본값 | 의미 |
| --- | --- | --- |
| `limit` | `50` | 가져올 개수, 1~100 |
| `offset` | `0` | 앞에서 건너뛸 개수, 0 이상 |
| `project_status` | `active` | `active`: 활성, `archived`: 보관, `all`: 전체 |

예를 들어 `GET /projects?limit=50&offset=0&project_status=all`은 본인의 활성·보관
프로젝트를 처음부터 최대 50개 조회합니다. 다음 페이지는 `offset=50`입니다.
`all`은 조회 옵션이며 DB에 저장하는 상태값은 아닙니다.

목록의 각 항목과 상세 응답에는 `id`, `owner_id`, `project_name`, `description`,
`github_url`, `figma_url`, `notion_url`, `project_status`, `created_at`, `updated_at`이
포함됩니다. 프론트는 URL이 있는 서비스의 아이콘을 표시할 수 있습니다.
URL 등록은 외부 서비스 계정 로그인이나 데이터 동기화를 수행하지 않습니다.

상세 조회는 `GET /projects/5`처럼 프로젝트 번호를 넣습니다. 보관된 프로젝트도
상세 조회할 수 있습니다. 목록이 `200`과 `[]`를 반환하면 조건에 맞는 본인 프로젝트가 없는 것입니다.

### 수정: PATCH /projects/{project_id}

수정할 항목만 요청 본문에 넣습니다. 아래 예시는 이름·설명을 변경하고 Figma 링크를 제거합니다.

```json
{
  "project_name": "MOEUM 수정",
  "description": "수정한 프로젝트 설명",
  "figma_url": null
}
```

보내지 않은 항목은 유지합니다. 수정 가능한 항목은 이름·설명·세 URL이며, 보관된
프로젝트도 수정할 수 있습니다. 설명과 URL은 `null`로 비울 수 있지만 이름은
`null`이나 공백으로 바꿀 수 없습니다. URL의 빈 문자열도 링크 제거로 처리합니다.
`id`, `owner_id`, `project_status`, 날짜는 이 API로 수정할 수 없습니다.

변경 내용이 있으면 `updated_at`을 갱신합니다. 성공 응답은 `200`과 수정된 정보입니다.
같은 서버의 목록이나 상세 조회에서 **Execute를 다시 눌러** 변경을 확인하세요.
Swagger의 이전 조회 결과는 자동으로 새로고침되지 않습니다.

### 보관 및 보관 해제

`PATCH /projects/5/archive`는 상태를 `archived`로 바꿉니다. DB 행, 이름, 설명과 URL은
유지되며 기본 목록에서는 빠집니다. `GET /projects?project_status=archived`로 확인합니다.

`PATCH /projects/5/restore`는 상태를 `active`로 바꾸며 기본 목록에 다시 표시됩니다.
두 API 모두 요청 본문은 없습니다. 이미 같은 상태라면 변경 없이 `200`을 반환합니다.

### 삭제: DELETE /projects/{project_id}

`DELETE /projects/5`는 해당 프로젝트를 DB에서 **영구 삭제**합니다. 보관과 달리
복원할 수 없으므로 삭제 확인 화면은 프론트에서 제공하고, Swagger 테스트에는
테스트용 프로젝트를 사용하세요. 요청 본문은 없습니다.

성공 시 `204`이고 응답 본문이 비어 있는 것이 정상입니다. 삭제 후 목록을 다시
조회하면 제외되고, 같은 프로젝트 상세 조회 또는 재삭제는 `404`를 반환합니다.

### 오류 응답과 테스트 순서

| 코드 | 의미 |
| --- | --- |
| `401` | 토큰 없음·만료·유효하지 않음: 다시 로그인하고 Authorize에 입력 |
| `403` | 생성 요청의 `owner_id`가 로그인한 회원과 다름 |
| `404` | 프로젝트가 없거나 다른 회원 소유임 |
| `422` | 입력 형식 오류: 이름·URL·프로젝트 번호·페이지 옵션 등 확인 |

테스트는 **생성 → 목록·상세 조회 → 수정 → 재조회 → 보관 → 보관 목록 조회 →
보관 해제 → 삭제 → 재조회** 순서로 진행합니다. 생성한 `id`를 계속 사용하고,
각 단계의 Server response 코드와 실제 응답을 확인합니다.

새 DB는 `sql/schema.sql`로 준비합니다. 기존 DB에 URL 컬럼이 없다면
`sql/migrate_project_urls.sql`을 한 번 실행합니다. 이미 컬럼이 있으면 다시 실행하지
마세요. 배포 환경의 DB에도 동일한 컬럼이 필요합니다.
자동 검증은 `python -m unittest discover -s tests -v`로 실행할 수 있습니다.
추가 설명은 [프로젝트 API 안내](docs/project-api.md)를 참고하세요.

## 비밀번호 찾기

이메일 확인 → 6자리 인증번호 발송·확인 → 새 비밀번호 설정 API를 제공합니다.
요청 형식, 화면 연결 순서, Gmail API 설정은 [비밀번호 찾기 API 안내](docs/password-reset-api.md)를 참고하세요.

## 로그인 API

회원가입과 로그인은 같은 MySQL `users` 테이블을 사용합니다. 로그인 세션은
`auth_sessions`에 저장합니다. 기존 DB에는 `sql/schema.sql`을 다시 실행하여
세션 테이블을 추가할 수 있습니다. 기존 회원 데이터는 유지됩니다.

기존 `users`에 `name` 컬럼이 없다면 아래 명령으로 컬럼과 세션 테이블을
준비합니다. 기존 회원의 초기 이름에는 아이디를 사용합니다.

```bash
python -m scripts.setup_login_db
```

`POST /api/auth/login`에 다음 JSON을 전송합니다. 회원가입 때 사용한 이메일과
비밀번호를 입력하세요.

```json
{
  "email": "testuser@example.com",
  "password": "test-password-123"
}
```

성공하면 `200`과 `access_token`, `token_type`, `expires_in`(3600초), `user`가
반환됩니다. 비밀번호 오류, 등록되지 않은 이메일, 비활성 계정은 동일한 `401` 응답을
반환하며 잘못된 입력 형식은 `422`입니다.

반환된 토큰을 아래 헤더에 넣어 요청합니다.

```text
Authorization: Bearer <access_token>
```

- `GET /api/auth/me`: 로그인한 회원 정보 조회
- `POST /api/auth/logout`: 현재 세션 삭제, 성공 시 `204`

Swagger `/docs`에서 로그인 후 **Authorize** 버튼에 토큰을 입력하여 테스트할
수 있습니다. 토큰은 1시간 뒤 만료되고 로그아웃한 토큰은 즉시 사용할 수 없습니다.
DB에는 원본 토큰 대신 SHA-256 해시를 저장하고 날짜는 UTC로 저장합니다.
여러 번 로그인하면 각각 독립된 세션이 생성됩니다.

인증 구현 참고: [FastAPI 공식 보안 문서](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
이 프로젝트는 JWT 대신 DB에서 확인하고 삭제할 수 있는 세션 토큰을 사용합니다.

FastAPI를 이용한 백엔드 API 연습 및 협업용 프로젝트입니다.

## 개발 환경

- Python 3.x
- FastAPI
- Uvicorn
- IntelliJ IDEA

## 폴더 구조

```text
fastapi-practice/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ routers/
│  │  ├─ __init__.py
│  │  └─ projects.py
│  ├─ schemas/
│  │  ├─ __init__.py
│  │  └─ project.py
│  ├─ services/
│  │  └─ __init__.py
│  └─ models/
│     └─ __init__.py
├─ requirements.txt
├─ README.md
└─ .gitignore
```

### 각 폴더의 의미와 역할

상위 폴더는 그 아래에 있는 파일과 폴더를 묶는 공간입니다. 예를 들어
`app/routers/projects.py`에서 `app`은 `routers`의 상위 폴더이고,
`routers`는 `projects.py`가 들어 있는 폴더입니다.

| 폴더 | 상위 폴더 | 의미와 역할 |
| --- | --- | --- |
| `fastapi-practice/` | 프로젝트를 보관한 외부 폴더 | 프로젝트의 최상위 폴더(루트)입니다. 애플리케이션 코드와 실행·설정·안내 파일을 모두 포함합니다. 터미널에서 서버 실행 명령을 입력하는 기준 위치입니다. |
| `app/` | `fastapi-practice/` | 실제 FastAPI 애플리케이션 코드를 모으는 폴더입니다. `main.py`에서 앱을 생성하고 각 기능의 라우터를 등록합니다. |
| `app/routers/` | `app/` | 클라이언트의 요청을 받는 API 경로와 처리 함수를 모으는 폴더입니다. `projects.py`에는 프로젝트 관련 API를 작성합니다. |
| `app/schemas/` | `app/` | API 요청과 응답의 데이터 형식을 정의하는 폴더입니다. Pydantic 모델로 필드와 유효성 검사 규칙을 작성하며, `project.py`에는 프로젝트 관련 스키마를 정의합니다. |
| `app/services/` | `app/` | 요청 처리에 필요한 비즈니스 로직을 모으는 폴더입니다. 프로젝트 처리나 GitHub·Figma·Notion 같은 외부 서비스 연동 로직을 작성합니다. |
| `app/models/` | `app/` | 데이터베이스에 저장할 데이터의 구조를 정의하는 폴더입니다. 데이터베이스 연동 시 테이블과 연결되는 모델을 작성합니다. |

각 폴더의 `__init__.py`는 해당 폴더를 Python 패키지로 인식하게 하는 파일입니다.
이를 통해 `from app.routers import projects`처럼 다른 모듈에서 코드를 가져올 수 있습니다.

루트에 있는 `requirements.txt`는 설치할 Python 패키지 목록,
`README.md`는 프로젝트 안내 문서, `.gitignore`는 Git에서 제외할 파일과 폴더의 규칙을 담습니다.

현재 회원가입·로그인·로그아웃·비밀번호 재설정과 프로젝트 CRUD·보관 API가 구현되어 있습니다.
API는 `.env`로 설정한 MySQL을 사용하며, 서버 실행 시 테이블을 자동 생성하지 않습니다.
기존 `pyproject.toml`과 `uv.lock`은 프로젝트 루트에 유지합니다.

## 실행 방법

### 1. 프로젝트 Clone

```bash
git clone https://github.com/0hyeona/fastapi-practice.git
```

프로젝트 폴더로 이동합니다.

```bash
cd fastapi-practice
```

### 2. 가상환경 생성

```bash
python -m venv .venv
```

### 3. 가상환경 활성화

Windows

```bash
.venv\Scripts\activate
```

Mac / Linux

```bash
source .venv/bin/activate
```

가상환경이 활성화되면 터미널 앞에 아래와 같이 표시됩니다.

```text
(.venv)
```

### 4. 패키지 설치

```bash
pip install -r requirements.txt
```

### 5. MySQL 설정

MySQL에서 `sql/schema.sql`을 실행하여 `moeum` 데이터베이스와 `users` 테이블을
준비합니다. 이미 있는 테이블은 이 파일로 변경되지 않습니다.

프로젝트 루트의 `.env.example`을 `.env`라는 이름으로 복사하고,
본인의 MySQL 접속 정보로 수정합니다. Windows 터미널에서는 다음을 실행합니다.

```powershell
Copy-Item .env.example .env
```

이미 `.env`가 있으면 복사하지 말고 기존 설정을 사용합니다.
`.env`의 실제 비밀번호는 GitHub에 올리지 않습니다.

### 6. FastAPI 서버 실행

```bash
fastapi dev app/main.py
```

명령어가 동작하지 않는 경우 아래 명령어를 사용합니다.

```bash
python -m uvicorn app.main:app --reload
```

### 7. 서버 확인

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000
```

### 8. Swagger API 문서 확인

FastAPI에서 자동으로 생성되는 Swagger 문서는 아래 주소에서 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

Swagger에서 현재 구현된 API를 확인하고 직접 테스트할 수 있습니다.

## 회원가입 테스트

서버 실행 후 `http://127.0.0.1:8000/docs`에서 `POST /api/auth/signup`을 열고
**Try it out**을 눌러 다음 JSON을 입력합니다.

```json
{
  "user_id": "testuser",
  "name": "테스트 회원",
  "email": "testuser@example.com",
  "password": "test-password-123"
}
```

아이디와 이름은 앞뒤 공백을 제거한 뒤 1~50자, 비밀번호는 8~128자여야 합니다.
이메일은 올바른 이메일 형식이어야 합니다. 성공 시 `201`, 아이디 또는 이메일
중복 시 `409`, 입력 형식 오류 시 `422`를 반환합니다. 비밀번호는 Argon2로 해싱해
저장하고 응답에는 비밀번호와 해시값을 포함하지 않습니다.

회원가입 관련 파일:

- `app/models/user.py`: 기존 users 테이블 매핑
- `app/schemas/auth.py`: 요청 검사 및 응답 형식
- `app/services/auth_service.py`: 중복 확인, 해싱, 저장
- `app/routers/auth.py`: 회원가입 API

자동 검증은 실제 MySQL 대신 임시 DB를 사용합니다.

```bash
python -m unittest discover -s tests -v
```

## 서버 종료

서버가 실행 중인 터미널에서 아래 단축키를 입력합니다.

```text
Ctrl + C
```

## 가상환경 종료

```bash
deactivate
```

## 패키지 추가 시

새로운 패키지를 설치한 경우 `requirements.txt`를 업데이트합니다.

```bash
pip freeze > requirements.txt
```

## Git 사용 시 참고

`.venv`, `.idea`, `.env` 등 개인 개발 환경 파일은 GitHub에 업로드하지 않습니다.

`.gitignore` 예시:

```gitignore
.venv/
.idea/
__pycache__/
.env
*.pyc
*.iml
```


## Story / Project Activities API

Story 작성·관리와 GitHub/Figma/Notion 변경사항 등록·관리 API: [사용 문서](docs/story-activity-api.md).
기존 DB에는 `sql/migrate_stories_activities.sql`을 먼저 적용합니다.

### GitHub dashboard

DB 테이블, IntelliJ 연결, 신규 API 실행 방법: [GitHub dashboard guide](docs/github-dashboard-api.md).

### Figma / Notion integrations

변경사항 수집, 서버 토큰 설정 및 Swagger 사용법: [연동 안내](docs/figma-notion-sync.md).

- 수집 실행 이력 및 DB 추가 방법: [project-sync-runs.md](docs/project-sync-runs.md)
- Notion 수집 시점, 문장 수정 전후 비교 및 기록 제외 기준은 아래 **Notion 변경사항 수집 기준**을 참고하세요.

## Notion 변경사항 수집 기준

Notion의 연결된 페이지를 읽는 **수집 실행**과, 이전에 저장한 내용과 달라진 부분을
`project_activities`에 남기는 **변경 기록 생성**은 별개입니다.
새로고침에 성공해도 달라진 본문이 없으면 새 기록은 0개입니다.

### 1. 언제 수집을 실행하나요?

| 상황 | Notion API 수집 실행 | 동작 |
| --- | --- | --- |
| Notion URL을 넣어 프로젝트 생성 | 설정이 맞으면 백그라운드에서 시도 | 최초 비교 기준을 저장합니다. 프로젝트 저장 성공이 수집 성공을 보장하지는 않습니다. |
| 프로젝트의 Notion URL 저장·교체 | 설정이 맞으면 백그라운드에서 시도 | 같은 URL을 다시 저장해도 시도할 수 있습니다. 다른 페이지는 별도 비교 기준을 사용합니다. |
| 현재 프론트에서 활성 프로젝트를 처음 불러옴 | URL이 있으면 시도 | `ProjectsContext`가 Notion 수집 후 저장된 목록을 조회합니다. 프로젝트 또는 Notion URL 변경도 실행 조건입니다. |
| MOEUM의 Notion 새로고침 버튼 클릭 | 실행 | 수집 API를 호출한 뒤 저장된 변경사항 목록을 다시 조회합니다. |
| 브라우저 전체 새로고침으로 프론트가 다시 마운트됨 | 활성 프로젝트와 URL이 준비되면 시도 | Notion 페이지를 수정하지 않았다면 새 기록은 생기지 않습니다. |
| `POST /api/projects/{project_id}/notion/sync` 직접 호출 | 실행 | 로그인과 프로젝트 접근 권한, 페이지 접근 설정을 검사합니다. |
| `GET /api/projects/{project_id}/activities?source=notion` | 실행하지 않음 | 이미 DB에 저장된 기록만 조회합니다. 대시보드·연결 상태의 GET API도 수집 명령이 아닙니다. |
| 프로젝트 이름·설명만 변경 | 해당 저장 요청에서는 실행하지 않음 | Notion URL 저장과 구분합니다. |
| 같은 프로젝트에서 화면만 이동 | 이것만으로 실행하지 않음 | 프론트가 재마운트되거나 수집 효과의 의존 값이 바뀌는 경우는 위 조건을 따릅니다. |
| Notion에서 편집만 하고 MOEUM을 사용하지 않음 | 실행하지 않음 | 현재 주기적 수집 스케줄러·Notion 변경 웹훅은 없습니다. |
| Notion 계정 승인·연결만 완료 | 계정 연결 API 자체에서는 실행하지 않음 | 페이지 URL 저장 또는 수동 새로고침으로 수집을 실행하세요. |

Notion URL이 없거나, 프로젝트 소유자의 Notion 연결·호환 서버 토큰 설정이 맞지 않으면
수집을 진행할 수 없습니다. OAuth 연결에서는 해당 연결이 접근할 수 있는 페이지여야 합니다.
서버 토큰 방식은 `NOTION_TOKEN`, `NOTION_TOKEN_OWNER_ID`, `NOTION_ALLOWED_PAGE_IDS`도 검사합니다.
URL을 아는 것만으로 비공개 페이지의 읽기 권한이 생기지는 않습니다.

### 2. 언제 변경 기록을 만드나요?

첫 수집은 페이지 제목과 블록별 본문을 `project_notion_snapshots`에 저장합니다.
비교할 이전 내용이 없으므로 기존 문서를 전부 '추가된 내용'으로 기록하지 않습니다.
두 번째 수집부터 저장된 기준과 새로 읽은 내용을 비교합니다.

| 수집 전후의 차이 | 생성되는 기록 | 화면에 표시할 내용 |
| --- | --- | --- |
| 같은 블록의 기존 문장을 다른 문장으로 수정 | `content_updated` · 내용 수정 | `수정 전`과 `수정 후`의 실제 문장 |
| 새 블록에 본문을 작성하거나 기존 빈 문단에 글을 입력 | `content_added` · 내용 추가 | `추가된 내용` |
| 본문이 있는 블록을 삭제하거나 기존 문장을 모두 지움 | `content_deleted` · 내용 삭제 | `삭제된 내용`에 이전 문장 보존 |
| 페이지 제목 수정 | `title_changed` · 제목 변경 | 이전 제목과 변경한 제목 |
| 본문이 있는 체크박스의 체크 상태 변경 | `content_updated` · 내용 수정 | `[ ] 할 일` → `[x] 할 일`처럼 전후 내용 |
| 이미지·파일·동영상 등 요소 추가·삭제 | 내용 추가 또는 삭제 | `[이미지]`, `[파일]` 등 요소 종류와 제공된 캡션. 이미지 내부 픽셀·문자를 자동 분석하는 기능은 아닙니다. |
| 수식 또는 표 셀의 본문 변경 | 내용 수정 등 | API에서 읽은 수식 표현식 또는 셀 텍스트의 차이 |

문장 비교는 **블록 ID**를 기준으로 합니다. 기존 문단의 글자를 고치면 수정 전후로 비교하지만,
문단 자체를 삭제하고 새 문단을 만들면 서로 다른 블록이므로 삭제와 추가로 나뉠 수 있습니다.
기존 문장이 없는 추가 기록에 임의의 '수정 전 문장'을 만들지는 않습니다.

### 3. 언제 새 기록을 만들지 않나요?

| 상황 | 처리 |
| --- | --- |
| 최초 수집 또는 처음 연결한 다른 페이지 | 기준만 저장하고 변경 기록은 만들지 않습니다. |
| 저장한 제목·비교 대상 본문과 동일 | 중복 기록을 만들지 않습니다. |
| 엔터로 만든 빈 문단, 공백만 있는 블록의 추가·삭제 | 본문 변경 기록에서 제외합니다. |
| 본문이 없는 체크박스의 추가 또는 체크만 변경 | 빈 문장 변경으로 기록하지 않습니다. |
| 모든 셀이 빈 표 행의 추가·삭제 | 빈 본문 기록을 만들지 않습니다. |
| 단·표·동기화 블록 같은 구조 컨테이너 자체의 추가 | 컨테이너만으로 본문 기록을 만들지 않습니다. 읽을 수 있는 하위 블록의 본문은 따로 비교합니다. |
| 글꼴·색상·굵기·블록 종류·배치만 바뀌고 비교 본문은 동일 | 현재 문장 비교 범위에서는 새 기록을 만들지 않습니다. |
| API가 지원하지 않는 블록 | 내용을 임의로 추정하지 않습니다. 이미 같은 ID로 저장된 본문은 보존합니다. 처음부터 읽을 수 없던 본문은 비교 기준으로 확정하지 않습니다. |

빈 블록·구조만 달라진 경우에도 정상 수집한 현재 상태는 다음 비교 기준으로 저장합니다.
본문 변경이 없다는 사실과 수집 실패를 구분합니다.

### 4. 수정 전후 비교 예시와 확인 순서

1. Notion 페이지 URL과 읽기 권한을 연결합니다.
2. MOEUM에서 **Notion 새로고침**을 눌러 현재 본문을 기준으로 저장합니다.
3. Notion에서 **기존 문단의 문장**을 수정합니다.
4. MOEUM에서 **Notion 새로고침**을 다시 누릅니다.
5. 변경사항 카드에서 다음과 같이 실제 문장이 구분되는지 확인합니다.

```text
수정 전: 전시회 날짜는 11월 20일입니다.
수정 후: 전시회 날짜는 11월 21일입니다.
```

수집 사이에 문장을 여러 번 수정했다면 마지막으로 수집한 문장과 이번에 수집한 문장만 비교합니다.
예를 들어 수집 전에 A → B → C로 수정했다면 A → C만 기록할 수 있으며,
A → B → A로 돌아오면 관측된 차이가 없어 기록이 생기지 않을 수 있습니다.
Notion의 전체 과거 버전 이력이나 모든 키 입력을 복원하는 기능은 아닙니다.

### 5. 수집 실패·본문 누락·페이지 교체 시 처리

- 권한 오류, 토큰 오류, 요청 한도, 시간 초과, 잘못된 응답, 하위 블록 조회 실패 시
  부분 수집 내용을 성공한 비교 기준으로 저장하지 않습니다. 기존 본문과 활동 기록을 유지합니다.
- 문단 등 텍스트 블록에서 필수 텍스트 필드가 빠지면 '빈 문장'으로 간주하지 않고 수집 실패로 처리합니다.
- 수집 시작과 끝의 페이지 제목·수정 시각이 다르면 수집 도중 바뀐 것으로 보고 저장하지 않습니다.
  편집이 끝난 뒤 새로고침하세요.
- 같은 프로젝트의 Notion 수집은 프로젝트 DB 잠금으로 순차 처리합니다.
- 시도 결과는 `project_sync_runs`에 남습니다. `GET /api/projects/{project_id}/sync-runs`로 확인할 수 있습니다.
- 페이지 URL을 바꾸면 새 페이지 ID의 별도 기준을 사용합니다. 이전 페이지 기록은 DB에 유지하지만,
  현재 연결한 페이지 기준의 Notion 활동 조회에서는 제외합니다. 하위 페이지를 자동으로 같은 페이지로 취급하지 않습니다.
- 이미 본문 없이 저장된 옛 기록은 이번 수정으로 과거 문장을 복원할 수 없습니다.
  화면의 '텍스트가 없는 블록이거나 상세 내용이 제공되지 않았어요'는 과거 기록에 표시할 본문이 없을 때의
  프론트 안내 문구이며, Notion이 직접 반환한 오류 메시지가 아닙니다.

### 6. 수집 범위와 DB/API

연결된 페이지 하나의 제목과 읽을 수 있는 하위 블록을 수집합니다.
하위 블록 목록은 페이지 끝까지 조회하고, 중첩 블록도 순회합니다.
별도 하위 페이지와 하위 데이터베이스의 내부 항목 전체는 순회하지 않으며 제목만 다룹니다.
파일 바이너리, 이미지 픽셀, 동영상 내용, 페이지 전체의 시각적 배치는 비교하지 않습니다.
안전상 중첩 깊이 50 초과 또는 블록 목록 요청 200회 초과 시 부분 결과를 저장하지 않고 실패 처리합니다.

| 저장 위치 / API | 역할 |
| --- | --- |
| `projects.notion_url` | 현재 연결한 페이지 URL |
| `project_notion_snapshots` | 프로젝트·페이지 ID별 마지막 정상 수집 본문과 비교 기준 |
| `project_activities` | 본문·제목 차이에서 생성한 변경 기록 |
| `project_sync_runs` | 수집 실행 성공·실패 이력 |
| `POST /api/projects/{project_id}/notion/sync` | 실제 수집 및 비교 실행 |
| `GET /api/projects/{project_id}/activities?source=notion&unorganized=true` | 현재 페이지의 미정리 기록 조회 |
| `GET /api/projects/{project_id}/integrations` | 연결 설정 상태 확인. 실제 페이지 읽기 성공을 보장하는 검사는 아닙니다. |

응답의 `fetched`와 `created`는 이 Notion 비교 흐름에서 생성한 변경 기록 수입니다.
읽은 전체 블록 수나 Notion API 호출 횟수가 아닙니다. 첫 기준 저장·변경 없음은 두 값 모두 0일 수 있습니다.

이 기능에는 위 테이블이 필요합니다. 서버 실행만으로 테이블을 자동 생성하지 않으므로
기존 설치는 [Notion 본문 비교 안내](docs/notion-content-diff.md)와
[수집 이력 안내](docs/project-sync-runs.md)의 스키마 준비 내용을 확인하세요.
이번 빈 본문·문장 비교 수정에는 추가 테이블이나 새 컬럼이 필요하지 않습니다.

구현: `app/services/notion_content.py`, `app/services/external_sync.py`,
`app/services/initial_sync.py`, `app/routers/project_integrations.py`.
프론트 실행 조건은 `moeum` 저장소의 `src/state/ProjectsContext.tsx`와
`src/api/externalActivities.ts`를 기준으로 합니다.

관련 검증은 임시 SQLite와 모의 API 응답으로 실행하며 실제 Notion 문서를 수정하지 않습니다.

```bash
python -m pytest tests/test_notion_content.py tests/test_external_sync.py tests/test_current_notion_page.py -q
```
>>>>>>> 7da31e5 (fix: Notion OAuth 인증 오류 및 배포 환경 연결 설정 개선)
