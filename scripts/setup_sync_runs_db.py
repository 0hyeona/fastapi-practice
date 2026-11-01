"""Inspect sync history schema; --apply creates only project_sync_runs."""
import argparse
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable, CreateIndex
from app.database.database import engine
from app.models.user import User  # Register referenced tables, without creating them.
from app.models.project import Project
from app.models.project_sync_run import ProjectSyncRun


def setup(connection, apply=False):
    table = ProjectSyncRun.__table__
    inspector = inspect(connection)
    if inspector.has_table(table.name):
        columns = {c["name"] for c in inspector.get_columns(table.name)}
        missing = set(table.columns.keys()) - columns
        if missing:
            raise RuntimeError("Existing project_sync_runs has missing columns: " + ", ".join(sorted(missing)))
        print("project_sync_runs already exists. No changes made.")
        return
    print(str(CreateTable(table).compile(dialect=connection.dialect)))
    for index in table.indexes:
        print(str(CreateIndex(index).compile(dialect=connection.dialect)))
    if apply:
        table.create(connection, checkfirst=True)
        connection.commit()
        print("Created project_sync_runs only. Existing tables and data preserved.")
    else:
        print("Inspection only. Run again with --apply to create the table.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    connection_engine = create_engine(engine.url, connect_args={"connect_timeout": 10})
    try:
        with connection_engine.connect() as connection:
            setup(connection, args.apply)
    except SQLAlchemyError:
        print("Database connection or DDL failed. Check DB connectivity, permissions and referenced projects table. Credentials omitted.")
        return 1
    finally:
        connection_engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
