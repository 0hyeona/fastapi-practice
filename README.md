# FastAPI Practice

FastAPI를 이용한 백엔드 API 연습 및 협업용 프로젝트입니다.

## 개발 환경

- Python 3.x
- FastAPI
- Uvicorn
- IntelliJ IDEA

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
fastapi dev main.py
```

명령어가 동작하지 않는 경우 아래 명령어를 사용합니다.

```bash
python -m fastapi dev main.py
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