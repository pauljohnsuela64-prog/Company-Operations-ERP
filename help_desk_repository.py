# ==========================================================
# IT MANAGEMENT - HELP DESK REPOSITORY
# ==========================================================

import uuid
import logging
from contextlib import contextmanager
from mysql.connector import Error
from help_desk_validation import HelpDeskError, identifier, create_values, resolution_value, listing_values

from database import get_connection


# ==========================================================
# GET ACTIVE TICKET CATEGORIES
# ==========================================================

def get_active_helpdesk_categories():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                category_id,
                category_code,
                category_name,
                description

            FROM helpdesk_categories

            WHERE is_active = TRUE

            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ALL TICKETS
# ==========================================================

def get_all_helpdesk_tickets():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                t.ticket_id,
                t.ticket_number,

                t.employee_id,
                e.employee_number,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS employee_name,

                t.department_id,
                d.department_name,

                t.category_id,
                c.category_code,
                c.category_name,

                t.subject,
                t.description,

                t.priority,
                t.status,

                t.assigned_to,
                assigned_user.username
                    AS assigned_to_username,

                t.resolution,

                t.created_by,
                created_user.username
                    AS created_by_username,

                t.resolved_at,
                t.closed_at,

                t.created_at,
                t.updated_at

            FROM helpdesk_tickets t

            INNER JOIN employees e
                ON t.employee_id = e.employee_id

            LEFT JOIN departments d
                ON t.department_id = d.department_id

            INNER JOIN helpdesk_categories c
                ON t.category_id = c.category_id

            LEFT JOIN users assigned_user
                ON t.assigned_to = assigned_user.user_id

            INNER JOIN users created_user
                ON t.created_by = created_user.user_id

            ORDER BY
                t.created_at DESC,
                t.ticket_id DESC
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET TICKET BY ID
# ==========================================================

def get_helpdesk_ticket_by_id(ticket_id):
    ticket_id = identifier(ticket_id)
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                t.*,

                e.employee_number,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS employee_name,

                d.department_name,

                c.category_code,
                c.category_name,

                assigned_user.username
                    AS assigned_to_username,

                created_user.username
                    AS created_by_username

            FROM helpdesk_tickets t

            INNER JOIN employees e
                ON t.employee_id = e.employee_id

            LEFT JOIN departments d
                ON t.department_id = d.department_id

            INNER JOIN helpdesk_categories c
                ON t.category_id = c.category_id

            LEFT JOIN users assigned_user
                ON t.assigned_to = assigned_user.user_id

            INNER JOIN users created_user
                ON t.created_by = created_user.user_id

            WHERE t.ticket_id = %s

            LIMIT 1
            """,
            (ticket_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET HELP DESK ASSIGNABLE USERS
# ==========================================================

def get_helpdesk_assignable_users():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                u.user_id,
                u.username,
                r.role_name

            FROM users u

            INNER JOIN roles r
                ON u.role_id = r.role_id

            WHERE
                u.is_active = TRUE
                AND r.role_name IN (
                    'Super Admin',
                    'IT Manager'
                )

            ORDER BY
                r.role_name,
                u.username
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()









# ==========================================================
# HELP DESK SUMMARY
# ==========================================================

def get_helpdesk_summary():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_tickets,

                COALESCE(
                    SUM(status = 'OPEN'),
                    0
                ) AS open_count,

                COALESCE(
                    SUM(status = 'IN_PROGRESS'),
                    0
                ) AS in_progress_count,

                COALESCE(
                    SUM(status = 'RESOLVED'),
                    0
                ) AS resolved_count,

                COALESCE(
                    SUM(status = 'CLOSED'),
                    0
                ) AS closed_count,

                COALESCE(
                    SUM(status = 'CANCELLED'),
                    0
                ) AS cancelled_count

            FROM helpdesk_tickets
            """
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# FILTER / SEARCH HELP DESK TICKETS
# ==========================================================



# ==========================================================
# GET TICKET HISTORY
# ==========================================================



# ==========================================================
# FILTER / SEARCH HELP DESK TICKETS
# ==========================================================

def get_filtered_helpdesk_tickets(
    search_text=None,
    status=None,
    priority=None,
    category_id=None,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        query = """
            SELECT
                t.ticket_id,
                t.ticket_number,

                t.employee_id,
                e.employee_number,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS employee_name,

                t.department_id,
                d.department_name,

                t.category_id,
                c.category_code,
                c.category_name,

                t.subject,
                t.description,

                t.priority,
                t.status,

                t.assigned_to,
                assigned_user.username
                    AS assigned_to_username,

                t.created_at,
                t.updated_at

            FROM helpdesk_tickets t

            INNER JOIN employees e
                ON t.employee_id = e.employee_id

            LEFT JOIN departments d
                ON t.department_id = d.department_id

            INNER JOIN helpdesk_categories c
                ON t.category_id = c.category_id

            LEFT JOIN users assigned_user
                ON t.assigned_to = assigned_user.user_id

            WHERE 1 = 1
        """

        parameters = []


        # ==================================================
        # SEARCH
        # ==========================================================

        if search_text:

            search_value = f"%{search_text}%"

            query += """
                AND (
                    t.ticket_number LIKE %s
                    OR t.subject LIKE %s
                    OR t.description LIKE %s
                    OR CONCAT(
                        e.first_name,
                        ' ',
                        e.last_name
                    ) LIKE %s
                    OR d.department_name LIKE %s
                    OR c.category_name LIKE %s
                    OR assigned_user.username LIKE %s
                )
            """

            parameters.extend(
                [
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                ]
            )


        # ==================================================
        # STATUS
        # ==========================================================

        if status:

            query += """
                AND t.status = %s
            """

            parameters.append(
                status
            )


        # ==================================================
        # PRIORITY
        # ==========================================================

        if priority:

            query += """
                AND t.priority = %s
            """

            parameters.append(
                priority
            )


        # ==================================================
        # CATEGORY
        # ==========================================================

        if category_id is not None:

            query += """
                AND t.category_id = %s
            """

            parameters.append(
                category_id
            )


        query += """
            ORDER BY
                t.created_at DESC,
                t.ticket_id DESC
        """

        cursor.execute(
            query,
            tuple(parameters),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET TICKET HISTORY
# ==========================================================

def get_helpdesk_ticket_history(ticket_id):
    ticket_id = identifier(ticket_id)
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                h.history_id,
                h.ticket_id,
                h.action_type,
                h.old_status,
                h.new_status,
                h.details,

                h.changed_by,

                u.username AS changed_by_username,

                h.created_at

            FROM helpdesk_ticket_history h

            INNER JOIN users u
                ON h.changed_by = u.user_id

            WHERE h.ticket_id = %s

            ORDER BY
                h.created_at DESC,
                h.history_id DESC
            """,
            (ticket_id,),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()

# ==========================================================
# HELP DESK REPORT - BY CATEGORY
# ==========================================================

def get_helpdesk_report_by_category():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                c.category_id,
                c.category_code,
                c.category_name,

                COUNT(t.ticket_id) AS total_tickets,

                COALESCE(
                    SUM(t.status = 'OPEN'),
                    0
                ) AS open_count,

                COALESCE(
                    SUM(t.status = 'IN_PROGRESS'),
                    0
                ) AS in_progress_count,

                COALESCE(
                    SUM(t.status = 'RESOLVED'),
                    0
                ) AS resolved_count,

                COALESCE(
                    SUM(t.status = 'CLOSED'),
                    0
                ) AS closed_count,

                COALESCE(
                    SUM(t.status = 'CANCELLED'),
                    0
                ) AS cancelled_count

            FROM helpdesk_categories c

            LEFT JOIN helpdesk_tickets t
                ON c.category_id = t.category_id

            GROUP BY
                c.category_id,
                c.category_code,
                c.category_name

            ORDER BY
                c.category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# HELP DESK REPORT - BY TECHNICIAN
# ==========================================================

def get_helpdesk_report_by_technician():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                t.assigned_to,

                COALESCE(
                    u.username,
                    'Unassigned'
                ) AS technician_name,

                COUNT(t.ticket_id) AS total_tickets,

                COALESCE(
                    SUM(t.status = 'OPEN'),
                    0
                ) AS open_count,

                COALESCE(
                    SUM(t.status = 'IN_PROGRESS'),
                    0
                ) AS in_progress_count,

                COALESCE(
                    SUM(t.status = 'RESOLVED'),
                    0
                ) AS resolved_count,

                COALESCE(
                    SUM(t.status = 'CLOSED'),
                    0
                ) AS closed_count,

                COALESCE(
                    SUM(t.status = 'CANCELLED'),
                    0
                ) AS cancelled_count

            FROM helpdesk_tickets t

            LEFT JOIN users u
                ON t.assigned_to = u.user_id

            GROUP BY
                t.assigned_to,
                u.username

            ORDER BY
                technician_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()

@contextmanager
def _transaction():
    connection = get_connection()  # Existing schema gate; no raw connection bypass.
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        _check_storage(cursor)
        yield cursor
        connection.commit()
    except Error as error:
        _rollback(connection)
        if error.errno == 1062:
            raise HelpDeskError('A ticket number already exists. Reload and verify before retrying.', 409) from None
        if error.errno == 1452:
            raise HelpDeskError('A referenced employee, category or user is no longer available.', 409) from None
        if error.errno in (1205, 1213):
            raise HelpDeskError('Help Desk records were busy. Reload and verify before retrying.', 409) from None
        raise HelpDeskError('Could not confirm the save. Reload and verify before retrying.', 503) from error
    except Exception:
        _rollback(connection)
        raise
    finally:
        failed = False
        try:
            if cursor is not None: cursor.close()
        except Error:
            failed = True
        try:
            connection.close()
        except Error:
            failed = True
        if failed:
            raise HelpDeskError('Could not confirm the save. Reload and verify before retrying.', 503) from None


def _rollback(connection):
    try:
        connection.rollback()
    except Error:
        pass  # Uncertain commit is never proof of noncommit or safe automatic replay.


def _check_storage(cursor):
    tables = ('helpdesk_tickets','helpdesk_ticket_history','helpdesk_categories','employees','departments','users','roles')
    cursor.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN (' + ','.join(['%s']*len(tables)) + ')', tables)
    engines = {row['TABLE_NAME']:row['ENGINE'] for row in cursor.fetchall()}
    if any(engines.get(table) != 'InnoDB' for table in tables):
        logging.getLogger(__name__).error('Help Desk storage incompatible: required InnoDB tables missing or unsupported.')
        raise HelpDeskError('Help Desk is temporarily unavailable. Contact an administrator.', 503)
    cursor.execute("SELECT NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS names,MAX(COALESCE(SUB_PART,0)) AS prefix_length FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='helpdesk_tickets' GROUP BY INDEX_NAME,NON_UNIQUE")
    if not any(row['NON_UNIQUE']==0 and row['names']=='ticket_number' and not row['prefix_length'] for row in cursor.fetchall()):
        logging.getLogger(__name__).error('Help Desk storage incompatible: full ticket-number unique index required.')
        raise HelpDeskError('Help Desk is temporarily unavailable. Contact an administrator.', 503)


def _history(cursor, identity, action, old, new, details, actor):
    cursor.execute('INSERT INTO helpdesk_ticket_history(ticket_id,action_type,old_status,new_status,details,changed_by) VALUES(%s,%s,%s,%s,%s,%s)', (identity,action,old,new,details,actor))


def create_helpdesk_ticket(employee_id, department_id, category_id, subject, description, priority, created_by):
    data = create_values(dict(employee_id=employee_id,category_id=category_id,subject=subject,description=description,priority=priority))
    actor = identifier(created_by, 'User')
    expected_department = identifier(department_id, 'Department') if department_id is not None else None
    with _transaction() as cursor:
        cursor.execute('SELECT department_id FROM employees WHERE employee_id=%s FOR SHARE', (data['employee_id'],))
        employee = cursor.fetchone()
        if employee is None:
            raise HelpDeskError('Employee not found.')
        department = employee['department_id']
        if expected_department is not None and expected_department != department:
            raise HelpDeskError('Employee Department changed. Reload before retrying.', 409)
        # Preserve the Employee's current Department snapshot, including an
        # inactive historical Department; do not invent employment eligibility.
        if department is not None:
            cursor.execute('SELECT department_id FROM departments WHERE department_id=%s FOR SHARE', (department,))
            if cursor.fetchone() is None:
                raise HelpDeskError('Employee Department is no longer available.', 409)
        cursor.execute('SELECT is_active FROM helpdesk_categories WHERE category_id=%s FOR SHARE', (data['category_id'],))
        category = cursor.fetchone()
        if not category or not category['is_active']:
            raise HelpDeskError('Selected category is invalid or inactive.')
        cursor.execute("INSERT INTO helpdesk_tickets(ticket_number,employee_id,department_id,category_id,subject,description,priority,status,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,'OPEN',%s)", (f'TMP-{uuid.uuid4().hex}',data['employee_id'],department,data['category_id'],data['subject'],data['description'],data['priority'],actor))
        identity = cursor.lastrowid
        number = f'HD-{identity:06d}'
        cursor.execute('UPDATE helpdesk_tickets SET ticket_number=%s WHERE ticket_id=%s', (number,identity))
        _history(cursor,identity,'CREATED',None,'OPEN','Ticket created',actor)
    return identity, number


def _ticket(cursor, identity):
    cursor.execute('SELECT ticket_id,status,assigned_to FROM helpdesk_tickets WHERE ticket_id=%s FOR UPDATE', (identity,))
    ticket = cursor.fetchone()
    if ticket is None:
        raise HelpDeskError('Help desk ticket was not found.', 404)
    return ticket


def assign_helpdesk_ticket(ticket_id, assigned_to, changed_by):
    identity, technician, actor = identifier(ticket_id), identifier(assigned_to,'Technician'), identifier(changed_by,'User')
    with _transaction() as cursor:
        # Lock eligibility rows before the ticket. Reassignment never needs two
        # technician locks, avoiding opposite-order technician swap deadlocks.
        cursor.execute('SELECT user_id,is_active,role_id FROM users WHERE user_id=%s FOR SHARE', (technician,))
        user = cursor.fetchone()
        if not user or not user['is_active']:
            raise HelpDeskError('Selected technician is invalid or inactive.')
        cursor.execute('SELECT role_name FROM roles WHERE role_id=%s FOR SHARE', (user['role_id'],))
        role = cursor.fetchone()
        if not role or role['role_name'] not in ('Super Admin','IT Manager'):
            raise HelpDeskError('Selected technician is invalid.')
        ticket = _ticket(cursor,identity)
        if ticket['status'] not in ('OPEN','IN_PROGRESS'):
            raise HelpDeskError('Resolved, closed, or cancelled tickets cannot be assigned.', 409)
        if ticket['assigned_to'] == technician:
            return False
        cursor.execute('UPDATE helpdesk_tickets SET assigned_to=%s WHERE ticket_id=%s', (technician,identity))
        _history(cursor,identity,'ASSIGNED',ticket['status'],ticket['status'],'Technician assigned or reassigned',actor)
    return True


def _transition(ticket_id, changed_by, action, resolution=None):
    identity, actor = identifier(ticket_id), identifier(changed_by,'User')
    if action == 'RESOLVE': resolution = resolution_value(resolution)
    before, after = {'START':('OPEN','IN_PROGRESS'),'RESOLVE':('IN_PROGRESS','RESOLVED'),'CLOSE':('RESOLVED','CLOSED')}[action]
    with _transaction() as cursor:
        ticket = _ticket(cursor,identity)
        if ticket['status'] != before:
            raise HelpDeskError({'START':'Only open tickets can be started.','RESOLVE':'Only tickets in progress can be resolved.','CLOSE':'Only resolved tickets can be closed.'}[action],409)
        if action == 'START' and ticket['assigned_to'] is None:
            raise HelpDeskError('Assign a technician before starting work.',409)
        if action == 'RESOLVE':
            cursor.execute("UPDATE helpdesk_tickets SET status='RESOLVED',resolution=%s,resolved_at=CURRENT_TIMESTAMP WHERE ticket_id=%s", (resolution,identity))
        elif action == 'CLOSE':
            cursor.execute("UPDATE helpdesk_tickets SET status='CLOSED',closed_at=CURRENT_TIMESTAMP WHERE ticket_id=%s", (identity,))
        else:
            cursor.execute("UPDATE helpdesk_tickets SET status='IN_PROGRESS' WHERE ticket_id=%s", (identity,))
        history_action = 'RESOLVED' if action == 'RESOLVE' else 'STATUS_CHANGE'
        details = resolution[:255] if action == 'RESOLVE' else ('Work started on ticket' if action=='START' else 'Ticket closed')
        _history(cursor,identity,history_action,before,after,details,actor)
    return True


def start_helpdesk_ticket(ticket_id, changed_by):
    return _transition(ticket_id,changed_by,'START')


def resolve_helpdesk_ticket(ticket_id, resolution, changed_by):
    return _transition(ticket_id,changed_by,'RESOLVE',resolution)


def close_helpdesk_ticket(ticket_id, changed_by):
    return _transition(ticket_id,changed_by,'CLOSE')


def get_all_helpdesk_categories():
    connection=get_connection()
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute('SELECT category_id,category_name,is_active FROM helpdesk_categories ORDER BY category_name,category_id')
            return cursor.fetchall()
    finally:
        connection.close()


def get_helpdesk_filter_users():
    # All referenced technicians remain filterable, regardless of current role or
    # active status. This list does not grant assignment eligibility.
    connection=get_connection()
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute('SELECT DISTINCT u.user_id,u.username,u.is_active FROM users u JOIN helpdesk_tickets t ON t.assigned_to=u.user_id ORDER BY u.username,u.user_id')
            return cursor.fetchall()
    finally:
        connection.close()


def get_helpdesk_ticket_page(filters):
    selected = listing_values(filters)
    where,params=['1=1'],[]
    if selected['search']:
        literal='%' + selected['search'].replace('!','!!').replace('%','!%').replace('_','!_') + '%'
        columns=('t.ticket_number','t.subject','t.description','e.employee_number',"CONCAT(e.first_name,' ',e.last_name)",'d.department_name','c.category_name','assigned_user.username')
        where.append('('+' OR '.join(column+" LIKE %s ESCAPE '!'" for column in columns)+')')
        params.extend([literal]*len(columns))
    for key,column in (('status','t.status'),('priority','t.priority'),('category_id','t.category_id')):
        if selected[key]:where.append(column+'=%s');params.append(selected[key])
    if selected['assigned_to']=='unassigned':where.append('t.assigned_to IS NULL')
    elif selected['assigned_to']:where.append('t.assigned_to=%s');params.append(selected['assigned_to'])
    joins=' FROM helpdesk_tickets t JOIN employees e ON e.employee_id=t.employee_id LEFT JOIN departments d ON d.department_id=t.department_id JOIN helpdesk_categories c ON c.category_id=t.category_id LEFT JOIN users assigned_user ON assigned_user.user_id=t.assigned_to WHERE '+' AND '.join(where)
    connection=get_connection()
    cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        _check_storage(cursor)
        cursor.execute('SELECT COUNT(*) AS total_tickets,'+','.join("COALESCE(SUM(t.status='"+status+"'),0) AS "+status.lower()+'_count' for status in ('OPEN','IN_PROGRESS','RESOLVED','CLOSED','CANCELLED'))+joins,tuple(params))
        summary=cursor.fetchone()
        pages=max(1,(summary['total_tickets']+selected['page_size']-1)//selected['page_size'])
        selected['page']=min(selected['page'],pages)
        cursor.execute("SELECT t.*,e.employee_number,CONCAT(e.first_name,' ',e.last_name) AS employee_name,d.department_name,c.category_name,assigned_user.username AS assigned_to_username"+joins+' ORDER BY t.created_at DESC,t.ticket_id DESC LIMIT %s OFFSET %s',(*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        return dict(records=cursor.fetchall(),summary=summary,pages=pages,**selected)
    finally:
        try:connection.rollback()
        finally:
            try:
                if cursor is not None:cursor.close()
            finally:connection.close()
