import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

# 프로젝트 루트의 .env에서 DB 접속 정보를 읽습니다.
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)

# URL.create를 사용하면 비밀번호에 특수문자가 있어도 안전하게 처리됩니다.
DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 3306)),
    database=os.getenv("DB_NAME"),
    query={"charset": "utf8mb4"},
)

# MySQL 연결을 관리합니다. 실제 연결은 DB 작업을 할 때 시작됩니다.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# API 요청에서 사용할 DB 세션을 만드는 설정입니다.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# models 폴더의 테이블 클래스가 상속할 공통 기반 클래스입니다.
Base = declarative_base()


def get_db():
    """FastAPI의 Depends(get_db)로 세션을 제공하고, 요청 종료 시 닫습니다."""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
