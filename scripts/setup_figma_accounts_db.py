"""Inspect the existing Figma table; create only this table with --apply."""
import argparse

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable

from app.database.database import engine
from app.models.user import User  # register the referenced table
from app.models.figma_account import FigmaAccount


def setup(connection, apply=False):
    table = FigmaAccount.__table__
    inspector = inspect(connection)
    if inspector.has_table(table.name):
        columns = inspector.get_columns(table.name)
        missing = set(table.columns.keys()) - {column['name'] for column in columns}
        if missing:
            raise RuntimeError('Existing figma_accounts schema differs. Missing columns: '
                               + ', '.join(sorted(missing))
                               + '. Keep the table and align its schema/model before deployment.')
        unique_keys = [inspector.get_pk_constraint(table.name)['constrained_columns']]
        unique_keys += [key['column_names'] for key in inspector.get_unique_constraints(table.name)]
        unique_keys += [key['column_names'] for key in inspector.get_indexes(table.name) if key['unique']]
        if ['user_id'] not in unique_keys:
            raise RuntimeError('figma_accounts.user_id must be PRIMARY KEY or UNIQUE; no changes made.')
        required_extra = [column['name'] for column in columns
                          if column['name'] not in table.columns and not column['nullable']
                          and column.get('default') is None and not column.get('autoincrement')
                          and not column.get('computed')]
        if required_extra:
            raise RuntimeError('Existing figma_accounts has additional required columns: '
                               + ', '.join(sorted(required_extra)) + '; align the model first.')
        print('figma_accounts already exists; schema checked, no changes made.')
        return
    print(CreateTable(table).compile(dialect=connection.dialect))
    if apply:
        table.create(connection, checkfirst=True)
        connection.commit()
        print('Created figma_accounts only.')
    else:
        print('Inspection only; run again with --apply if this table does not exist.')


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
        print('Database inspection/setup failed. Check connectivity and permissions. Credentials omitted.')
        return 1
    finally:
        target.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
