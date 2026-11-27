# 모음 (moeum) 백엔드

> GitHub 커밋, Figma 디자인 수정, Notion 문서 변경을 프로젝트별로 수집하고, 선택한 변경사항을 하나의 **Story**로 저장하는 FastAPI 서버입니다.

**팀원** 고지운, 김현아, 송연지

## 목차

- [프로젝트 링크 및 서버 정보](#프로젝트-링크-및-서버-정보)
- [프로젝트 소개](#프로젝트-소개)
- [기술 스택](#기술-스택-tech-stack)
- [주요 API](#주요-api)
- [프로젝트 구조](#프로젝트-구조)
- [설치 및 실행 방법](#설치-및-실행-방법)
- [환경변수](#환경변수)
- [테스트](#테스트)

## 프로젝트 링크 및 서버 정보

| **구분** | **용도** | **링크** |
| --- | --- | --- |
| 백엔드 저장소 | FastAPI 서버 코드와 DB 스키마 확인 | [0hyeona/fastapi-practice](https://github.com/0hyeona/fastapi-practice) |
| 배포 API · Render | 서버 API 호출 및 Swagger에서 요청·응답 테스트 | [API 주소](https://fastapi-practice-jwse.onrender.com/) · [Swagger UI](https://fastapi-practice-jwse.onrender.com/docs) |
| 배포 사이트 · Vercel | 로그인하고 프로젝트와 Story 이용하기 | [모음 열기](https://moeum-log.vercel.app/) |

## 프로젝트 소개

로그인 오류 안내를 개선한 작업을 예로 들면, 화면 문구는 Figma에, 구현한 코드는 GitHub 커밋에, 문구를 바꾼 이유는 Notion에 남을 수 있습니다. 모음 백엔드는 같은 프로젝트에서 선택한 기록으로 Story 초안을 만듭니다. 작성자가 내용을 다듬어 저장하면 Story에 원본 변경사항이 연결되어, 팀원이 나중에 변경 이유와 구현 내역을 함께 살펴볼 수 있습니다.

## 기술 스택 (Tech Stack)

### Backend

**`🐍 Python`** **`⚡ FastAPI`** **`🦄 Uvicorn`** **`✅ Pydantic`** **`🌐 HTTPX`**

### Database

**`🐬 MySQL`** **`🗄️ TiDB`** **`🔗 SQLAlchemy`** **`🔌 PyMySQL`**

### Authentication

**`🔐 Argon2`** **`🔑 OAuth 2.0`** **`🎟️ DB 세션 토큰`**

### DevOps & Tools

**`☁️ Render`** **`🐙 GitHub`** **`📖 Swagger UI`** **`🧪 pytest`**

<details>
<summary>버전 정보 보기</summary>

Python 3.12 이상에서 실행합니다. [pyproject.toml](./pyproject.toml)

API 서버에는 FastAPI 0.142.2, Uvicorn 0.54.0, Pydantic 2.13.5를 사용합니다. DB 연결에는 SQLAlchemy 2.1.3과 PyMySQL 1.2.3을 사용합니다. [requirements.txt](./requirements.txt)

</details>

## 주요 API

| 기능 | 대표 요청 | 서버에서 처리하는 내용 |
| --- | --- | --- |
| 회원 인증 | `POST /api/auth/login` · `POST /api/auth/refresh` · `GET /api/auth/me` | 이메일·GitHub 로그인 후 마지막 갱신부터 30일간 유지하며, 접속 중 자동 갱신하고 브라우저 재실행 시 쿠키로 복원합니다. [로그인 유지 정책](./docs/session-expiration.md)을 참고하세요. 비밀번호 재설정 인증번호는 Gmail API로 발송합니다. |
| 프로젝트 | `POST /projects` · `GET /projects` | 내가 소유하거나 공유받은 프로젝트를 조회합니다. 소유자는 프로젝트를 수정·보관·복원·삭제할 수 있습니다. [프로젝트 API](./docs/project-api.md) |
| 멤버 공유 | `POST /api/projects/{project_id}/members` | 소유자가 가입 이메일로 팀원을 추가합니다. 팀원은 기록과 Story를 조회하고 소유자의 연결로 Notion을 다시 수집할 수 있습니다. [멤버 권한표](./docs/project-sharing.md#api와-권한) |
| 대시보드와 변경사항 | `GET /api/projects/{project_id}/dashboard` · `GET /api/projects/{project_id}/activities` | 서비스별 미정리 개수와 최근 활동을 조회합니다. 활동 목록에 `unorganized=true`를 주면 Story에 연결할 기록만 가져옵니다. |
| Story 작성 | `POST /stories/analyze` · `POST /stories` | 같은 프로젝트의 기록 1~20개로 초안을 만듭니다. 내용을 확인한 뒤 저장 요청에 `activity_ids`를 보내면 Story와 선택한 기록이 함께 연결됩니다. |
| Story 조회와 내보내기 | `GET /api/projects/{project_id}/stories` · `GET /stories/{story_id}/export` | 저장된 Story를 최신순으로 조회하거나 한 편을 Markdown 파일로 내려받습니다. |

Story 초안은 저장된 활동의 제목·설명과 GitHub에서 확인한 변경 파일 및 diff를 규칙 기반으로 정리합니다. 외부 AI 키 없이 제목, 요약, 태그와 확인 가능한 코드의 변경 전후를 반환합니다. [초안 생성 코드](./app/services/story_analysis.py) · [Story 요청·응답 예시](./docs/story-api.md#s7-생성-및-활동-연결)

### 서비스별 변경사항 수집

| 서비스 | 수집 방식 | 관련 문서 |
| --- | --- | --- |
| GitHub | `POST /api/projects/{project_id}/github/sync`로 선택한 브랜치의 커밋을 저장합니다. 이미 수집한 커밋은 기존 Story와의 연결을 유지합니다. | [GitHub 대시보드와 수집](./docs/github-dashboard-api.md) |
| Figma | 소유자가 발급한 일회용 코드로 플러그인을 연결합니다. `POST /api/figma-plugin/snapshot`으로 받은 첫 파일 상태를 기준으로 삼아 이후 편집을 비교합니다. 파일 버전의 수동 수집에는 사용자별 OAuth를 사용합니다. | [플러그인 연결](./docs/figma-live-plugin.md) · [Figma OAuth](./docs/figma-user-oauth.md) |
| Notion | 페이지 URL을 저장하면 접근 권한을 확인해 첫 수집을 시도합니다. 첫 수집은 비교 기준을 저장하고, 이후 `POST /api/projects/{project_id}/notion/sync`를 호출하면 제목 변경과 본문 추가·수정·삭제를 기록합니다. | [Notion 본문 비교](./docs/notion-content-diff.md) · [Notion OAuth](./docs/notion-user-oauth.md) |

프로젝트에 등록한 서비스 URL은 `GET /api/projects/{project_id}/connections`에서, 수집 시각과 성공·실패 이력은 `GET /api/projects/{project_id}/sync-runs`에서 확인합니다. [연결 정보 API](./docs/project-connections-api.md) · [수집 이력](./docs/project-sync-runs.md)

## 프로젝트 구조

```text
fastapi-practice/
├── app/
│   ├── main.py          # FastAPI 앱 생성, 라우터 및 CORS 등록
│   ├── routers/         # 인증, 프로젝트, 서비스 연동, Story API
│   ├── schemas/         # 요청·응답 형식과 입력 검증
│   ├── services/        # 권한 검사, 변경 수집·비교, Story 생성 및 내보내기
│   ├── models/          # 회원, 세션, 프로젝트, 변경사항, Story 등의 DB 모델
│   └── database/        # DB 접속 설정과 요청별 SQLAlchemy 세션
├── sql/                 # 기본 스키마와 기존 DB용 마이그레이션
├── scripts/             # 기능별 테이블 점검 및 생성
├── tests/               # API, 인증, 수집 규칙 테스트
├── docs/                # 기능별 설정과 API 사용 예시
├── .env.example         # 로컬 및 배포에 쓰는 환경변수 예시
└── requirements.txt     # 서버 실행 의존성
```

## 설치 및 실행 방법

### 1. Python 환경 준비

아래 명령은 Python 3.12 이상이 설치된 Windows PowerShell 기준입니다. 처음 내려받을 때는 백엔드 개발 브랜치를 복제합니다. 기존 작업본이 있다면 해당 저장소의 루트에서 가상환경 준비부터 시작합니다.

```sh
git clone --branch develop https://github.com/0hyeona/fastapi-practice.git
cd fastapi-practice
```

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

macOS·Linux에서는 `python3 -m venv .venv`로 생성한 뒤 `.venv/bin/python`을 사용합니다. Windows Git Bash에서는 `.venv/Scripts/python.exe`를 사용합니다. 두 셸 모두 `test -f .env || cp .env.example .env`로 환경 파일을 복사할 수 있습니다.

### 2. 개발 DB 연결

루트 `.env`에 개발용 MySQL 또는 TiDB의 `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`을 입력합니다. 팀에서 준비한 DB를 사용한다면 바로 서버 실행 단계로 이동합니다. 새 DB는 서버 실행 전에 아래 순서로 준비합니다. [DB 연결 코드](./app/database/database.py)

<details>
<summary>빈 개발 DB에서 처음 시작하는 경우</summary>

1. MySQL Workbench 등의 SQL 편집기에서 [sql/schema.sql](./sql/schema.sql)을 실행합니다. 기본 DB 이름은 `moeum`입니다. 다른 이름을 쓴다면 SQL의 `CREATE DATABASE`와 `USE` 대상도 `DB_NAME`과 맞춥니다.
2. 방금 생성한 `stories` 테이블에 현재 Story 모델이 사용하는 회고 본문과 분석 결과 컬럼을 추가합니다. 아래 SQL은 기본 스키마로 **새로 만든 DB에서 한 번** 실행합니다. 기존 DB에서는 `SHOW COLUMNS FROM stories`로 확인 후 누락된 컬럼만 추가합니다. [Story 모델](./app/models/story.py)

   ```sql
   ALTER TABLE stories
       ADD COLUMN why TEXT,
       ADD COLUMN problem TEXT,
       ADD COLUMN solution TEXT,
       ADD COLUMN result TEXT,
       ADD COLUMN learned TEXT,
       ADD COLUMN next_steps TEXT,
       ADD COLUMN ai_analysis JSON;
   ```

3. 저장소 루트의 PowerShell에서 다음 명령으로 나머지 모델 테이블을 생성합니다. 여기에는 프로젝트 목록 조회에 필요한 `project_members`, 수집 이력과 Figma·Notion 비교용 테이블이 포함됩니다.

   ```powershell
   .\.venv\Scripts\python.exe -c "import app.main; from app.database.database import Base, engine; Base.metadata.create_all(engine)"
   ```

</details>

### 3. 서버 실행과 Swagger 확인

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

1. [로컬 Swagger UI](http://127.0.0.1:8000/docs)를 엽니다. 처음이라면 `POST /api/auth/signup`에서 `user_id`, `name`, `email`, `password`로 개발용 회원을 생성합니다.
2. `POST /api/auth/login`에 이메일과 비밀번호를 입력합니다. 응답의 `access_token` 값만 복사해 상단 **Authorize**의 **Value**에 붙여 넣습니다.
3. `POST /projects`에 `{"project_name":"전시회 준비"}`를 보내면 `201`과 프로젝트 `id`를 받습니다. `GET /projects`에서 같은 `id`가 보이면 회원 인증과 DB 저장까지 확인한 것입니다.

## 환경변수

이메일 로그인과 기본 프로젝트 API는 DB 설정으로 시작할 수 있습니다. 외부 기능을 사용할 때는 아래 값을 로컬 `.env` 또는 Render 서비스의 **Environment**에 추가합니다. 변수 이름과 기본값은 [.env.example](./.env.example)에 있습니다.

| 사용 기능 | 환경변수 | 용도 |
| --- | --- | --- |
| 웹 앱 접근 | `FRONTEND_ORIGINS` | API 호출을 허용할 웹 출처를 쉼표로 구분합니다. 로컬 기본값은 `http://localhost:5173`과 `http://127.0.0.1:5173`입니다. |
| GitHub 로그인 | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`, `FRONTEND_AUTH_CALLBACK_URL`, `GITHUB_CREDENTIAL_ENCRYPTION_KEY` | GitHub는 백엔드의 `/api/auth/github/callback`으로 돌아옵니다. 웹 앱은 일회용 로그인 코드를 `POST /api/auth/github/exchange`에서 모음 세션으로 교환합니다. |
| Figma REST 수집 | `FIGMA_CLIENT_ID`, `FIGMA_CLIENT_SECRET`, `FIGMA_REDIRECT_URI`, `FIGMA_CREDENTIAL_ENCRYPTION_KEY` | 사용자별 Figma 계정 승인을 처리합니다. 편집기 플러그인은 별도의 프로젝트 연결 코드를 사용합니다. |
| Notion OAuth | `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET`, `NOTION_OAUTH_REDIRECT_URI`, `NOTION_CREDENTIAL_ENCRYPTION_KEY` | 소유자가 승인한 워크스페이스에서 프로젝트에 등록한 페이지를 읽습니다. |
| 비밀번호 재설정 메일 | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_FROM_EMAIL` | 발신 계정의 권한으로 회원 이메일에 인증번호를 보냅니다. [Gmail 발송 설정](./docs/password-reset-api.md#실제-이메일-발송-설정) |

OAuth 토큰 암호화 키는 서비스별로 한 번 생성해 재배포 후에도 같은 값을 사용합니다. 실제 비밀번호와 토큰은 개발 환경의 `.env` 또는 배포 환경변수에 보관합니다.

## 테스트

로그인 세션 발급·만료·로그아웃은 임시 SQLite DB로 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_login.py" -v
```

전체 테스트에는 pytest로 작성한 항목도 있습니다. 가상환경에 테스트 도구를 설치한 뒤 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
```
