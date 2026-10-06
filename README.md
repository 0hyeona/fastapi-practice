# FastAPI Practice

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
`GET /`이며, 프로젝트 API와 데이터베이스 연동은 추후 추가합니다.
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

### 5. FastAPI 서버 실행

```bash
fastapi dev app/main.py
```

명령어가 동작하지 않는 경우 아래 명령어를 사용합니다.

```bash
python -m uvicorn app.main:app --reload
```

### 6. 서버 확인

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000
```

### 7. Swagger API 문서 확인

FastAPI에서 자동으로 생성되는 Swagger 문서는 아래 주소에서 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

Swagger에서 현재 구현된 API를 확인하고 직접 테스트할 수 있습니다.

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
