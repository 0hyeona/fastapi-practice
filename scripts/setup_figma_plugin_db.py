"""Inspect/create only the two editor-plugin tables; never alter existing tables."""
import argparse

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable

from app.database.database import engine
from app.models.user import User  # register foreign keys
from app.models.project import Project
from app.models.figma_plugin import FigmaPluginConnection, ProjectFigmaSnapshot


def setup(connection, apply=False):
    tables = [FigmaPluginConnection.__table__, ProjectFigmaSnapshot.__table__]
    inspector = inspect(connection)
    missing_tables = []
    for table in tables:
        if not inspector.has_table(table.name):
            missing_tables.append(table)
            continue
        missing = set(table.columns.keys()) - {column['name'] for column in inspector.get_columns(table.name)}
        primary = inspector.get_pk_constraint(table.name)['constrained_columns']
        if missing or primary != ['project_id']:
            raise RuntimeError(f'{table.name}: schema mismatch; no changes made. '
                               f'Missing columns: {", ".join(sorted(missing)) or "none"}. Expected project_id primary key.')
    for table in missing_tables:
        print(CreateTable(table).compile(dialect=connection.dialect))
    if apply:
        for table in missing_tables:
            table.create(connection, checkfirst=True)
        connection.commit()
        print('Figma plugin tables ready. Existing activities/accounts were preserved.')
    else:
        print('Inspection only. Add --apply to create the missing plugin tables.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = create_engine(engine.url, connect_args={'connect_timeout': 10})
    try:
        with target.connect() as connection:
            setup(connection, args.apply)
    except RuntimeError as error:
        print(str(error))
        return 1
    except SQLAlchemyError:
        print('Database setup failed. Check connectivity and permissions. Credentials omitted.')
        return 1
    finally:
        target.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
