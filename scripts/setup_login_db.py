"""프로젝트 루트에서 python -m scripts.setup_login_db로 실행합니다."""

from sqlalchemy import inspect, text

from app.database.database import engine
from app.models.user import User
from app.models.auth_session import AuthSession


def main():
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "name" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN name VARCHAR(50) NOT NULL DEFAULT '' AFTER user_id"))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET name = user_id WHERE name = ''"))
    AuthSession.__table__.create(engine, checkfirst=True)
    print("Login database setup complete.")


if __name__ == "__main__":
    main()
