"""Explicit-target, read-only diagnostics. Exit 0 compatible, 1 mismatch, 2 unavailable."""
import argparse
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mysql.connector
from schema_compatibility import inspect_schema, MANIFEST_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('host', 'user', 'database'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    try:
        with mysql.connector.connect(host=args.host, port=args.port, user=args.user,
                                     database=args.database, password=getpass('MySQL password: '),
                                     connection_timeout=3, read_timeout=5, write_timeout=5) as connection:
            result = inspect_schema(connection, args.database)
            connection.rollback()
        print('Capability manifest:', MANIFEST_VERSION)
        for issue in result.issues:
            print('-', issue)
        print('Compatible.' if result.compatible else 'Incompatible; operator review required. No changes applied.')
        return 0 if result.compatible else 1
    except (mysql.connector.Error, ValueError, OSError):
        print('Inspection unavailable: verify target, connectivity and metadata access. No changes applied.')
        return 2


if __name__ == '__main__':
    sys.exit(main())
