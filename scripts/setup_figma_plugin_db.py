"""Create plugin tables or add the two nullable collection-status columns only."""
import argparse

from sqlalchemy import DateTime, String, create_engine, inspect, text
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
    additions = []
    for table in tables:
        if not inspector.has_table(table.name):
            missing_tables.append(table)
            continue
        columns = {column['name']: column for column in inspector.get_columns(table.name)}
        missing = set(table.columns.keys()) - columns.keys()
        if table.name == 'figma_plugin_connections':
            for name, sql_type in [('last_seen_at', 'DATETIME'), ('collection_state', 'VARCHAR(24)')]:
                if name in missing:
                    additions.append(f'ALTER TABLE figma_plugin_connections ADD COLUMN {name} {sql_type} NULL')
                    missing.remove(name)
                else:
                    column = columns[name]
                    compatible = (isinstance(column['type'], DateTime) if name == 'last_seen_at' else
                                  isinstance(column['type'], String) and column['type'].length == 24)
                    if not compatible or not column['nullable']:
                        raise RuntimeError(f'{table.name}.{name}: expected nullable {sql_type}; no changes made.')
        primary = inspector.get_pk_constraint(table.name)['constrained_columns']
        if missing or primary != ['project_id']:
            raise RuntimeError(f'{table.name}: schema mismatch; no changes made. '
                               f'Missing columns: {", ".join(sorted(missing)) or "none"}. Expected project_id primary key.')
    for table in missing_tables:
        print(CreateTable(table).compile(dialect=connection.dialect))
    for statement in additions:
        print(statement)
    if apply:
        for table in missing_tables:
            table.create(connection, checkfirst=True)
        for statement in additions:
            connection.execute(text(statement))
        connection.commit()
        print('Figma plugin tables ready. Existing activities/accounts were preserved.')
    else:
        print('Inspection only. Add --apply to create tables or add the listed nullable columns.')


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
    except (SQLAlchemyError, OSError):
        print('Database setup failed. Check connectivity and permissions. Credentials omitted.')
        return 1
    finally:
        target.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
