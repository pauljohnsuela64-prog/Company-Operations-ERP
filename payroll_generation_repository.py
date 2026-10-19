"""Policy-pinned cutoff generation; deliberately does not calculate payroll."""
import calendar
from datetime import date, datetime
import re
import uuid

from database import get_connection
from payroll_freshness import lock_payroll_inputs, raise_payroll_lock_error
from payroll_policy_repository import _decode
from payroll_policy_validation import (CONFIG_FIELDS, policy_values, positive_integer,
                                       require_resolved, verify_configuration_hash,
                                       company_today)


def month_cutoffs(year, month):
    year = positive_integer(year, 'Year', 9999)
    month = positive_integer(month, 'Month', 12)
    if year < 1000:
        raise ValueError('Year must be between 1000 and 9999.')
    return [dict(cutoff_code='A', start_date=date(year, month, 1), end_date=date(year, month, 15)),
            dict(cutoff_code='B', start_date=date(year, month, 16),
                 end_date=date(year, month, calendar.monthrange(year, month)[1]))]


def payment_date(value, end, label):
    if isinstance(value, datetime):
        raise ValueError(f'{label} must be a date without a time.')
    if not isinstance(value, date):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError(f'{label} is required in YYYY-MM-DD format.')
        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise ValueError(f'{label} is not a valid date.') from None
    if value.year < 1000 or value < end:
        raise ValueError(f'{label} must be a supported date on or after the cutoff end.')
    return value


def _resolve(cursor, cutoffs):
    # A locking current read avoids a pre-guard consistent-read snapshot.
    cursor.execute('''SELECT v.* FROM payroll_policy_activations a
        JOIN payroll_policy_versions v USING(policy_version_id)
        ORDER BY a.effective_from FOR UPDATE''')
    schedule = [_decode(row) for row in cursor.fetchall()]
    for cutoff in cutoffs:
        eligible = [row for row in schedule if row['effective_from'] <= cutoff['start_date']]
        if not eligible:
            raise ValueError(f"Cutoff {cutoff['cutoff_code']} has no activated policy covering its start.")
        policy = eligible[-1]
        if any(cutoff['start_date'] < row['effective_from'] <= cutoff['end_date'] for row in schedule):
            raise ValueError('A cutoff cannot straddle a policy activation boundary.')
        if policy['status'] != 'APPROVED':
            raise ValueError('Generation requires an APPROVED and activated policy.')
        require_resolved(policy_values({name: policy[name] for name in CONFIG_FIELDS}))
        verify_configuration_hash(policy)
        cutoff.update(policy_version_id=policy['policy_version_id'], version_number=policy['version_number'])
    return cutoffs


def generate_month(year, month, pay_date_a=None, pay_date_b=None, actor_id=None,
                   preview=False, timezone_name='Asia/Manila'):
    cutoffs = month_cutoffs(year, month)
    # Explicit company configuration is validated; no host-local date assumptions.
    company_today(timezone_name)
    if not preview:
        actor_id = positive_integer(actor_id, 'Acting user', 2147483647)
        for cutoff, value in zip(cutoffs, (pay_date_a, pay_date_b)):
            cutoff['pay_date'] = payment_date(value, cutoff['end_date'], f"Cutoff {cutoff['cutoff_code']} payment date")
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        lock_payroll_inputs(cursor)
        _resolve(cursor, cutoffs)
        if not preview:
            # Validate both cutoffs before writing either. Cancelled periods do not overlap.
            for cutoff in cutoffs:
                cursor.execute('''SELECT * FROM payroll_periods WHERE status <> 'CANCELLED'
                    AND start_date <= %s AND end_date >= %s ORDER BY payroll_period_id FOR UPDATE''',
                    (cutoff['end_date'], cutoff['start_date']))
                existing = cursor.fetchall()
                if existing:
                    if len(existing) != 1 or any(existing[0][key] != cutoff[key] for key in
                        ('start_date', 'end_date', 'pay_date', 'policy_version_id', 'cutoff_code')):
                        raise ValueError(f"Cutoff {cutoff['cutoff_code']} conflicts with an existing period's dates, payment date or policy. No periods were changed.")
                    cutoff.update(payroll_period_id=existing[0]['payroll_period_id'], created=False)
            for cutoff in cutoffs:
                if 'payroll_period_id' in cutoff:
                    continue
                token = uuid.uuid4().hex
                cursor.execute('''INSERT INTO payroll_periods
                    (period_number,period_name,start_date,end_date,pay_date,status,created_by,policy_version_id,cutoff_code)
                    VALUES(%s,%s,%s,%s,%s,'DRAFT',%s,%s,%s)''',
                    (f'TMP-{token}', f"{cutoff['start_date']:%Y-%m} cutoff {cutoff['cutoff_code']} {token[:12]}",
                     cutoff['start_date'],cutoff['end_date'],cutoff['pay_date'],actor_id,
                     cutoff['policy_version_id'],cutoff['cutoff_code']))
                identifier = cursor.lastrowid
                cursor.execute('UPDATE payroll_periods SET period_number=%s WHERE payroll_period_id=%s',
                               (f'PP-{identifier:06d}',identifier))
                cutoff.update(payroll_period_id=identifier, created=True)
        connection.commit()
        return cutoffs
    except Exception as error:
        connection.rollback()
        raise_payroll_lock_error(error)
        raise
    finally:
        cursor.close()
        connection.close()
