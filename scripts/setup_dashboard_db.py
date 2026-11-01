"""Inspect by default; --apply adds missing columns/index/FK without removing data."""
import argparse
from sqlalchemy import create_engine, inspect
from app.database.database import engine


def plan(connection):
    inspector = inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("project_activities")}
    statements = []
    for name, definition in {"story_id": "BIGINT UNSIGNED NULL", "external_id": "VARCHAR(255) NULL", "branch_name": "VARCHAR(255) NULL"}.items():
        if name not in columns:
            statements.append(f"ALTER TABLE project_activities ADD COLUMN {name} {definition}")
    foreign_keys = inspector.get_foreign_keys("project_activities")
    story_keys = [key for key in foreign_keys if key["constrained_columns"] == ["story_id"]]
    if story_keys:
        key = story_keys[0]
        if key["referred_table"] != "stories" or key["referred_columns"] != ["id"] or key.get("options", {}).get("ondelete", "").upper() != "SET NULL":
            raise RuntimeError("Existing story_id foreign key must reference stories.id ON DELETE SET NULL; review manually.")
    else:
        statements.append("ALTER TABLE project_activities ADD CONSTRAINT fk_dashboard_activity_story FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE SET NULL")
    indexes = inspector.get_indexes("project_activities")
    if not any(index["column_names"] == ["project_id", "story_id", "occurred_at"] for index in indexes):
        statements.append("CREATE INDEX idx_activities_unorganized ON project_activities (project_id, story_id, occurred_at)")
    return statements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    connection_engine = create_engine(engine.url, connect_args={"connect_timeout": 10})
    with connection_engine.connect() as connection:
        for table in ("projects", "stories", "project_activities"):
            print(table, [column["name"] for column in inspect(connection).get_columns(table)])
        statements = plan(connection)
        for statement in statements:
            print(statement + ";")
        if args.apply:
            for statement in statements:
                connection.exec_driver_sql(statement)
                connection.commit()
            print("Dashboard migration complete. Existing rows and updated_at column are preserved.")
        elif statements:
            print("Review the SQL above; run with --apply to execute it.")
        else:
            print("Required dashboard columns, index and foreign key already exist.")


if __name__ == "__main__":
    main()
