# FastAPI Practice

## 협업자 환경 설정

실제 비밀번호는 각자의 `.env`에 저장하고, GitHub에는 `.env.example`만 공유합니다.
처음 설정할 때 아래 명령을 실행하세요. 기존 `.env`가 있으면 덮어쓰지 마세요.

```powershell
Copy-Item .env.example .env
```

- `.env`의 DB 접속 정보와 SMTP 발송 계정 정보를 채웁니다.
- Gmail의 `SMTP_PASSWORD`에는 일반 비밀번호 대신 16자 앱 비밀번호를 입력합니다.
- 같은 발송 계정을 공유한다면 앱 비밀번호는 비밀번호 관리 도구의 보안 공유 기능으로 전달합니다.
- `.env`와 `tests/.env`는 Git에서 제외됩니다. 설정 후 서버를 재시작하세요.
- 현재 서버는 프로젝트 루트의 `.env`를 읽습니다. `tests/.env`는 읽지 않습니다.

## GitHub 로그인

`.env`에 같은 OAuth App의 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`,
`GITHUB_REDIRECT_URI`를 설정합니다. 로컬 callback은
`http://localhost:8000/api/auth/github/callback`입니다.

기존 DB에는 한 번 `python -m scripts.setup_github_db`를 실행하여 GitHub 회원 연결
테이블을 추가합니다. 새 DB에는 `sql/schema.sql`을 사용합니다.

1. 브라우저에서 `http://localhost:8000/api/auth/github/login`을 엽니다.
2. GitHub에 로그인하고 권한에 동의합니다.
3. callback 성공 응답의 `access_token`은 **우리 서비스 로그인 토큰**이며,
   `token_type`은 `bearer`, `expires_in`은 `3600`초입니다. GitHub 토큰은 반환하거나 저장하지 않습니다.
4. Swagger의 **Authorize**에 이 토큰만 입력하면 `/api/auth/me`, 프로젝트 API,
   `/api/auth/logout`을 기존 로그인과 동일하게 사용할 수 있습니다.

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
요청 형식, 화면 연결 순서, SMTP 설정은 [비밀번호 찾기 API 안내](docs/password-reset-api.md)를 참고하세요.

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
