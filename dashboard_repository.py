"""Permission-scoped, bounded dashboard reads; no business writes or repairs."""
from datetime import date
import logging
import mysql.connector
from database import get_connection, SchemaUnavailable

logger = logging.getLogger(__name__)

# Preserve original list readers' inner-join eligibility, omitting optional labels.
SECTIONS = {
    'employees': ('employees.view', 'employees e', 'e.employment_status',
                  {'active': 'ACTIVE', 'on_leave': 'ON LEAVE', 'inactive': 'INACTIVE'}, 'total'),
    'attendance': ('attendance.view', 'attendance_records a JOIN employees e ON e.employee_id=a.employee_id JOIN users u ON u.user_id=a.created_by', 'a.status',
                   {'present': 'PRESENT', 'late': 'LATE', 'absent': 'ABSENT', 'on_leave': 'ON_LEAVE', 'half_day': 'HALF_DAY'}, 'total'),
    'leave': ('leave.view', 'leave_requests lr JOIN employees e ON e.employee_id=lr.employee_id JOIN leave_types lt ON lt.leave_type_id=lr.leave_type_id JOIN users u ON u.user_id=lr.requested_by', 'lr.status',
              {'pending': 'PENDING', 'approved': 'APPROVED'}, None),
    'inventory': ('inventory.view', 'inventory_items i', None, {}, 'total_items'),
    'procurement': ('procurement.view', 'purchase_requests pr JOIN users u ON u.user_id=pr.requested_by', 'pr.status',
                    {'draft': 'DRAFT', 'pending_approval': 'SUBMITTED', 'approved': 'APPROVED'}, None),
    'finance': ('finance.view', 'expenses e JOIN expense_categories c ON c.category_id=e.category_id JOIN users u ON u.user_id=e.created_by', 'e.status',
                {'draft': 'DRAFT', 'approved': 'APPROVED', 'paid': 'PAID'}, None),
    'it_assets': ('it_assets.view', 'it_assets a JOIN it_asset_categories c ON c.category_id=a.category_id JOIN users u ON u.user_id=a.created_by', 'a.status',
                  {'available': 'AVAILABLE', 'assigned': 'ASSIGNED', 'maintenance': 'MAINTENANCE', 'lost': 'LOST'}, 'total'),
    'helpdesk': ('helpdesk.view', 'helpdesk_tickets t JOIN employees e ON e.employee_id=t.employee_id JOIN helpdesk_categories c ON c.category_id=t.category_id JOIN users u ON u.user_id=t.created_by', 't.status',
                 {'resolved': 'RESOLVED'}, 'total'),
    'payroll': ('payroll.view', 'payroll_periods pp JOIN users creator ON creator.user_id=pp.created_by', 'pp.status',
                {'draft': 'DRAFT', 'processing': 'PROCESSING', 'approved': 'APPROVED', 'paid': 'PAID'}, None),
}

# str.strip includes information separators as well as Unicode whitespace.
# Employment status is VARCHAR; other state columns are canonical ENUM values.
EMPLOYMENT_WHITESPACE = '^[[:space:]\\x1c-\\x1f]+|[[:space:]\\x1c-\\x1f]+$'


class SectionUnavailable(RuntimeError):
    pass


def _aggregate_query(section, today):
    _, source, column, states, total = SECTIONS[section]
    fields, parameters = [], []
    if total:
        fields.append(f'COUNT(*) AS {total}')
    for key, status in states.items():
        if section == 'employees':
            normalized = f'CAST(UPPER(REGEXP_REPLACE({column}, %s, %s)) AS BINARY)'
            parameters.extend((EMPLOYMENT_WHITESPACE, ''))
        else:
            normalized = f'CAST(UPPER(TRIM({column})) AS BINARY)'
        fields.append(f'COALESCE(SUM(CASE WHEN {normalized}=%s THEN 1 ELSE 0 END),0) AS {key}')
        parameters.append(status)
    if section == 'inventory':
        fields.append('COALESCE(SUM(CASE WHEN i.is_active<>0 THEN 1 ELSE 0 END),0) AS active_items')
    if section == 'helpdesk':
        fields.extend((
            'COALESCE(SUM(CASE WHEN t.status IN (%s,%s) THEN 1 ELSE 0 END),0) AS open',
            'COALESCE(SUM(CASE WHEN t.status IN (%s,%s) AND t.priority=%s THEN 1 ELSE 0 END),0) AS urgent_open'))
        parameters.extend(('OPEN', 'IN_PROGRESS', 'OPEN', 'IN_PROGRESS', 'URGENT'))
    query = 'SELECT ' + ','.join(fields) + ' FROM ' + source
    if section == 'attendance':
        query += ' WHERE a.attendance_date=%s'
        parameters.append(today)
    return query, tuple(parameters)


LATEST_PAID_SQL = """SELECT pp.payroll_period_id,pp.period_number,pp.period_name,
    pp.start_date,pp.end_date,pp.pay_date,pp.status,pp.notes,pp.created_at,
    pp.updated_at,pp.approved_at,pp.paid_at,
    creator.username AS created_by_username,updater.username AS updated_by_username,
    approver.username AS approved_by_username,payer.username AS paid_by_username
    FROM payroll_periods pp JOIN users creator ON creator.user_id=pp.created_by
    LEFT JOIN users updater ON updater.user_id=pp.updated_by
    LEFT JOIN users approver ON approver.user_id=pp.approved_by
    LEFT JOIN users payer ON payer.user_id=pp.paid_by
    WHERE CAST(UPPER(TRIM(pp.status)) AS BINARY)=%s
    ORDER BY pp.start_date DESC,pp.payroll_period_id DESC LIMIT 1"""


def _read_section(section, today):
    connection = get_connection()  # Fundamental failures must not become cards.
    cursor = None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ', consistent_snapshot=True, readonly=True)
        cursor = connection.cursor(dictionary=True)
        query, parameters = _aggregate_query(section, today)
        cursor.execute(query, parameters)
        result = {key: int(value) for key, value in cursor.fetchone().items()}
        if section == 'payroll':
            cursor.execute(LATEST_PAID_SQL, ('PAID',))
            result['latest_paid'] = cursor.fetchone()
        return result
    except mysql.connector.Error as error:
        logger.warning('Dashboard section %s failed (database error %s).', section, error.errno)
        if error.errno in (1054, 1146):  # Missing module column/table only.
            raise SectionUnavailable() from error
        raise SchemaUnavailable('Dashboard data unavailable.') from error
    finally:
        failed = False
        try:
            connection.rollback()
        except mysql.connector.Error:
            failed = True
        try:
            if cursor is not None:
                cursor.close()
        except mysql.connector.Error:
            failed = True
        try:
            connection.close()
        except mysql.connector.Error:
            failed = True
        if failed:
            raise SchemaUnavailable('Dashboard data unavailable.')


def get_dashboard_summary(permissions):
    """Use refreshed request permissions; absent/failed sections have no counts."""
    permissions = frozenset(permissions)
    today = date.today()
    summary = dict(today=today, **{section: None for section in SECTIONS})
    for section, (permission, *_) in SECTIONS.items():
        if permission not in permissions:
            continue
        try:
            summary[section] = _read_section(section, today)
        except SectionUnavailable:
            pass  # Explicit unavailable state; never fabricate zero counts.
    return summary
