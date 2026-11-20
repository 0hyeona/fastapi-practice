"""Create only the per-user Notion OAuth table when --apply is provided."""
import argparse
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable
from app.database.database import engine
from app.models.user import User  # register the referenced table
from app.models.notion_account import NotionAccount


def setup(connection, apply=False):
    table = NotionAccount.__table__
    inspector = inspect(connection)
    if inspector.has_table(table.name):
        missing = set(table.columns.keys()) - {c['name'] for c in inspector.get_columns(table.name)}
        if missing:
            raise RuntimeError('Missing Notion account columns: ' + ', '.join(sorted(missing)))
        print('user_notion_accounts already exists; no changes made.')
        return
    print(CreateTable(table).compile(dialect=connection.dialect))
    if apply:
        table.create(connection, checkfirst=True)
        connection.commit()
        print('Created user_notion_accounts only.')
    else:
        print('Inspection only; run again with --apply to create this table.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = create_engine(engine.url, connect_args={'connect_timeout': 10})
    try:
        with target.connect() as connection:
            setup(connection, args.apply)
    except SQLAlchemyError:
        print('Database operation failed. Check connectivity and permissions. Credentials omitted.')
        return 1
    finally:
        target.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
