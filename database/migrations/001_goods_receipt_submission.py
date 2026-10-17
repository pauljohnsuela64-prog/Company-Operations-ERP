"""Explicit, repeatable upgrade. Does not read ERP configuration or run on import."""
import argparse
from getpass import getpass

import mysql.connector


def upgrade(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COLUMN_TYPE, IS_NULLABLE, CHARACTER_SET_NAME, COLLATION_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='goods_receipts' AND column_name='submission_id'")
        column = cursor.fetchone()
        if column is None:
            cursor.execute("ALTER TABLE goods_receipts ADD COLUMN submission_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL, ADD CONSTRAINT uq_goods_receipts_submission UNIQUE (submission_id)")
            return
        if (column['COLUMN_TYPE'].lower() != 'char(36)' or column['IS_NULLABLE'] != 'YES'
                or column['CHARACTER_SET_NAME'] != 'ascii' or column['COLLATION_NAME'] != 'ascii_bin'):
            raise RuntimeError('Existing submission_id column is incompatible; inspect it manually before upgrading.')
        cursor.execute("SELECT INDEX_NAME, NON_UNIQUE, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns_list, MAX(COALESCE(SUB_PART,0)) AS prefix_length FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='goods_receipts' GROUP BY INDEX_NAME, NON_UNIQUE")
        indexes = cursor.fetchall()
        if any(row['NON_UNIQUE'] == 0 and row['columns_list'] == 'submission_id' and row['prefix_length'] == 0 for row in indexes):
            return
        if any(row['INDEX_NAME'] == 'uq_goods_receipts_submission' for row in indexes):
            raise RuntimeError('Index uq_goods_receipts_submission already exists with an incompatible definition.')
        cursor.execute("ALTER TABLE goods_receipts ADD CONSTRAINT uq_goods_receipts_submission UNIQUE (submission_id)")
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--user', required=True)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    password = getpass('MySQL password: ')
    with mysql.connector.connect(host=args.host, port=args.port, user=args.user,
                                 password=password, database=args.database) as connection:
        upgrade(connection)
    print('Goods receipt submission migration verified/applied.')


if __name__ == '__main__':
    main()
