# ==========================================================
# AUDIT LOG REPOSITORY
# ==========================================================

from database import get_connection
from datetime import date, datetime, time, timedelta
from mysql.connector import Error
from audit_log_validation import AuditLogError, filter_values


# ==========================================================
# CREATE AUDIT LOG
# ==========================================================

def create_audit_log(
    user_id,
    username,
    module,
    action,
    entity_type=None,
    entity_id=None,
    description=None,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO audit_logs (
                user_id,
                username,
                module,
                action,
                entity_type,
                entity_id,
                description
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                user_id,
                username,
                module,
                action,
                entity_type,
                (
                    str(entity_id)
                    if entity_id is not None
                    else None
                ),
                description,
            ),
        )


        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET FILTER OPTIONS
# ==========================================================

def get_audit_log_filter_options():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT DISTINCT module

            FROM audit_logs

            ORDER BY module
            """
        )

        module_rows = cursor.fetchall()


        cursor.execute(
            """
            SELECT DISTINCT action

            FROM audit_logs

            ORDER BY action
            """
        )

        action_rows = cursor.fetchall()


        return {
            "modules": [
                row["module"]
                for row in module_rows
            ],

            "actions": [
                row["action"]
                for row in action_rows
            ],
        }


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET FILTERED AUDIT LOGS
# ==========================================================

def get_filtered_audit_logs(search_text=None,module=None,action=None,start_date=None,end_date=None,page=1,page_size=25):
    """Compatibility list API, now bounded; use the page API for totals/navigation."""
    return get_audit_log_page(dict(search='' if search_text is None else search_text,
        module='' if module is None else module,action='' if action is None else action,
        start_date=start_date,end_date=end_date,page=page,page_size=page_size),include_options=False)['records']


def _check_audit_storage(cursor):
    cursor.execute("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='audit_logs'")
    row=cursor.fetchone()
    if not row or row['ENGINE']!='InnoDB':
        raise AuditLogError('Audit Logs are temporarily unavailable. Contact an administrator.',503)
    cursor.execute("SELECT NON_UNIQUE,COLUMN_NAME,SUB_PART FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='audit_logs' AND index_name='PRIMARY' ORDER BY SEQ_IN_INDEX")
    keys=cursor.fetchall()
    if len(keys)!=1 or keys[0]['NON_UNIQUE']!=0 or keys[0]['COLUMN_NAME']!='audit_log_id' or keys[0]['SUB_PART'] is not None:
        raise AuditLogError('Audit Logs are temporarily unavailable. Contact an administrator.',503)


def get_audit_log_page(filters,include_options=True):
    selected=filter_values(filters)  # Reject invalid filters before connecting.
    where,params=['1=1'],[]
    if selected['search']:
        literal='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        where.append('('+' OR '.join(column+" LIKE %s ESCAPE '!'" for column in ('username','module','action','entity_type','entity_id','description'))+')')
        params.extend([literal]*6)
    for key in ('module','action'):
        if selected[key]:where.append(key+'=%s');params.append(selected[key])
    if selected['start_date']:
        where.append('created_at >= %s');params.append(selected['start_date'])
    if selected['end_date']:
        if selected['end_date']==date.max:
            # DATE_ADD(maximum date, 1 day) becomes NULL in MySQL. Bind an
            # inclusive ceiling instead of dropping or overflowing this filter.
            where.append('created_at <= %s');params.append('9999-12-31 23:59:59.999999')
        else:
            where.append('created_at < %s');params.append(datetime.combine(selected['end_date']+timedelta(days=1),time.min))
    clause=' FROM audit_logs WHERE '+' AND '.join(where)
    connection=get_connection()  # Preserve existing global schema admission.
    cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        _check_audit_storage(cursor)
        cursor.execute('SELECT COUNT(*) AS total'+clause,tuple(params))
        total=cursor.fetchone()['total']
        pages=max(1,(total+selected['page_size']-1)//selected['page_size'])
        selected['page']=min(selected['page'],pages)
        cursor.execute('SELECT audit_log_id,user_id,username,module,action,entity_type,entity_id,description,created_at'+clause+
            ' ORDER BY created_at DESC,audit_log_id DESC LIMIT %s OFFSET %s',(*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        records=cursor.fetchall()
        options=dict(modules=[],actions=[])
        if include_options:
            cursor.execute('SELECT DISTINCT module FROM audit_logs ORDER BY module')
            options['modules']=[row['module'] for row in cursor.fetchall()]
            cursor.execute('SELECT DISTINCT action FROM audit_logs ORDER BY action')
            options['actions']=[row['action'] for row in cursor.fetchall()]
        first=(selected['page']-1)*selected['page_size']+1 if total else 0
        return dict(records=records,total=total,pages=pages,first=first,last=first+len(records)-1 if records else 0,filters=selected,**options)
    except Error as error:
        raise AuditLogError('Audit Logs are temporarily unavailable. Please retry later.',503) from error
    finally:
        failed=False
        try:connection.rollback()  # End read-only snapshot; never commit history.
        except Error:failed=True
        try:
            if cursor is not None:cursor.close()
        except Error:failed=True
        try:connection.close()
        except Error:failed=True
        if failed:raise AuditLogError('Audit Logs are temporarily unavailable. Please retry later.',503) from None
