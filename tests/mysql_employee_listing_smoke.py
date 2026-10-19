"""Actual Employee prefix search/collation/pagination; disposable MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import time
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
import employee_repository as repo


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='')
    with mysql.connector.connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE employee_listing CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
    options['database']='employee_listing'
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as db:
            cur=db.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();return result
    text=(harness.ROOT/'database/core_schema.sql').read_text()
    for stmt in re.sub(r'--[^\n]*','',text).split(';'):
        if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',stmt,re.I):sql(stmt)
    with patch.object(repo,'get_connection',side_effect=connect):
        assert repo.get_employee_page()['total']==0
        assert repo.get_employee_page(page=999)['page']==1
    rows=[(f'LIST-{i:03d}','Same','Tie',None) for i in range(63)]
    rows += [('PCT%ID','José',"O'Neil",'Middle'),('PCT_ID','Unicode名字','Zebra',None),
             ('PCT!ID','<script>unsafe</script>','Zebra',None),('PCTXID','Other','Zebra',None)]
    with connect() as db:
        cur=db.cursor();cur.executemany('INSERT INTO employees(employee_number,first_name,last_name,middle_name) VALUES(%s,%s,%s,%s)',rows);db.commit()
    def snapshot():return sql('SELECT * FROM employees ORDER BY employee_id',fetch=True)
    before=snapshot()
    for mode in ('STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE',''):
        options['init_command']="SET SESSION sql_mode='"+mode+"'"
        with patch.object(repo,'get_connection',side_effect=connect):
            assert len(repo.get_employee_page()['employees'])==25
            for term,total in [('LIST-',63),('list-',63),('Same',63),('Tie',63),('josé',1),
                               ('JOSE',1),("O'",1),('Unicode名',1),('Middle',1),('PCT%',1),
                               ('PCT_',1),('PCT!',1),("' OR 1=1 --",0),('%',0),('_',0),('missing',0)]:
                result=repo.get_employee_page(term)
                assert result['total']==total,(term,result['total'])
                assert len(result['employees'])<=25
            expected=sql("SELECT employee_id FROM employees WHERE employee_number LIKE 'LIST-%' ORDER BY last_name,first_name,employee_id",fetch=True)
            actual=[(e['employee_id'],) for page in (1,2,3) for e in repo.get_employee_page('LIST-',page)['employees']]
            assert actual==expected and len(set(actual))==63
            assert repo.get_employee_page('LIST-',999999999)['page']==3
            assert len(repo.get_employee_page('LIST-',3)['employees'])==13
            assert repo.get_employee_page('   ')['total']==67
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:repo.get_employee_page('LIST-',2),range(12)))
            assert all(result==results[0] for result in results)
        assert snapshot()==before
        print('PASS default/empty, literal prefix/Unicode/punctuation/injection, stable tied names, pages/counts, concurrent reads and no changes in',mode or 'NON-STRICT')
    # Explicit binary-column fixture proves queries defer to column collation.
    sql('ALTER TABLE employees MODIFY COLUMN first_name VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL')
    with patch.object(repo,'get_connection',side_effect=connect):
        assert repo.get_employee_page('josé')['total']==0
        assert repo.get_employee_page('José')['total']==1
    print('PASS explicit case-sensitive column collation')
    print('Indexes:',sql('SHOW INDEX FROM employees',fetch=True))
    with patch.object(repo,'get_connection',side_effect=connect):
        for target in (67,1000,5000):
            if target>67:
                current=sql('SELECT COUNT(*) FROM employees',fetch=True)[0][0]
                with connect() as db:
                    cur=db.cursor();cur.executemany("INSERT INTO employees(employee_number,first_name,last_name) VALUES(%s,'Scale','Fixture')",[(f'SCALE-{i}',) for i in range(current,target)]);db.commit()
            started=time.perf_counter()
            result=repo.get_employee_page('SCALE-',page=2)
            elapsed=(time.perf_counter()-started)*1000
            assert len(result['employees'])<=25
            print(f'PERFORMANCE synthetic rows={target}, count+page+connection={elapsed:.2f}ms, returned={len(result["employees"])}')


if __name__=='__main__':
    harness.run=run
    harness.main()
