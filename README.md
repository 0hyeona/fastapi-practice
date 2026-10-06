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

프로젝트 라우터와 스키마는 기본 틀만 준비되어 있습니다. 현재 구현된 API는
`GET /`와 `POST /api/auth/signup`입니다. 회원가입은 `.env`로 설정한 MySQL의
기존 `users` 테이블을 사용하며, 서버 실행 시 테이블을 자동 생성하지 않습니다.
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
