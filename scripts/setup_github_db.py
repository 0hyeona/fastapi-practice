"""프로젝트 루트에서 python -m scripts.setup_github_db로 실행합니다."""

from app.database.database import engine
from app.models.user import User
from app.models.auth_session import AuthSession
from app.models.github_account import GithubAccount


def main():
    GithubAccount.__table__.create(engine, checkfirst=True)
    AuthSession.__table__.create(engine, checkfirst=True)
    print("GitHub login database setup complete.")


if __name__ == "__main__":
    main()
