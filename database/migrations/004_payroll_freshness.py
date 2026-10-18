"""Explicit repeatable upgrade; never reads ERP configuration or runs on import."""
import argparse
from getpass import getpass
import mysql.connector


def upgrade(connection):
    cursor=connection.cursor(dictionary=True)
    try:
        for table in ['payroll_periods','payroll_entries','payroll_adjustments','employees','attendance_records','leave_requests','leave_types']:
            cursor.execute('SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s',(table,))
            row=cursor.fetchone()
            if not row or row['ENGINE']!='InnoDB':raise RuntimeError(f'{table} must exist and use InnoDB before upgrading.')
        for name,definition,column_type,charset,collation in [
            ('calculation_input_version','SMALLINT UNSIGNED NULL','smallint unsigned',None,None),
            ('calculation_input_hash','CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL','char(64)','ascii','ascii_bin')]:
            cursor.execute("SELECT COLUMN_TYPE,IS_NULLABLE,CHARACTER_SET_NAME,COLLATION_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='payroll_entries' AND column_name=%s",(name,))
            row=cursor.fetchone()
            if row is None:
                cursor.execute(f'ALTER TABLE payroll_entries ADD COLUMN {name} {definition}')
            elif (row['COLUMN_TYPE'].lower()!=column_type or row['IS_NULLABLE']!='YES' or row['CHARACTER_SET_NAME']!=charset or row['COLLATION_NAME']!=collation):
                raise RuntimeError(f'Existing {name} is incompatible; manual review required.')
        cursor.execute('CREATE TABLE IF NOT EXISTS payroll_input_guard (guard_id TINYINT NOT NULL PRIMARY KEY) ENGINE=InnoDB')
        cursor.execute("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='payroll_input_guard'")
        if cursor.fetchone()['ENGINE']!='InnoDB':raise RuntimeError('Payroll coordination table must use InnoDB.')
        cursor.execute("SELECT COLUMN_TYPE,IS_NULLABLE,COLUMN_KEY FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='payroll_input_guard' AND column_name='guard_id'")
        row=cursor.fetchone()
        if not row or row['COLUMN_TYPE'].lower()!='tinyint' or row['IS_NULLABLE']!='NO' or row['COLUMN_KEY']!='PRI':raise RuntimeError('Incompatible coordination table; manual review required.')
        cursor.execute("SELECT COLUMN_NAME FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='payroll_input_guard' AND index_name='PRIMARY' ORDER BY SEQ_IN_INDEX")
        if [r['COLUMN_NAME'] for r in cursor.fetchall()]!=['guard_id']:raise RuntimeError('Incompatible coordination primary key.')
        cursor.execute("SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='payroll_input_guard'")
        if [r['COLUMN_NAME'] for r in cursor.fetchall()]!=['guard_id']:raise RuntimeError('Unexpected coordination columns; manual review required.')
        cursor.execute('INSERT IGNORE INTO payroll_input_guard(guard_id) VALUES(1)')
        connection.commit()
    finally:
        cursor.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['host','user','database']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',required=True,type=int)
    args=parser.parse_args()
    with mysql.connector.connect(host=args.host,port=args.port,user=args.user,password=getpass('MySQL password: '),database=args.database) as connection:
        upgrade(connection)
    print('Payroll freshness upgrade applied/verified; no historical evidence was backfilled.')


if __name__=='__main__':main()
