"""Versioned policy management. No salary calculation or period generation."""
import json

from database import get_connection
from payroll_freshness import lock_payroll_inputs, raise_payroll_lock_error
from payroll_policy_validation import (CONFIG_FIELDS, JSON_RULES, approval_reference,
    company_today, configuration_hash, effective_date, policy_values, positive_integer,
    require_resolved, verify_configuration_hash)


def _decode(row):
    if row:
        for name in JSON_RULES:
            if isinstance(row[name], (str, bytes)):
                try: row[name] = json.loads(row[name])
                except (ValueError, RecursionError):
                    raise ValueError('Stored policy configuration is invalid. Contact an administrator.') from None
    return row


def get_policy(policy_id):
    policy_id = positive_integer(policy_id, 'Policy ID', 2147483647)
    connection = get_connection(); cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM payroll_policy_versions WHERE policy_version_id=%s', (policy_id,))
        return _decode(cursor.fetchone())
    finally:
        cursor.close(); connection.close()


def list_policies():
    connection = get_connection(); cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM payroll_policy_versions ORDER BY version_number DESC')
        return [_decode(row) for row in cursor.fetchall()]
    finally:
        cursor.close(); connection.close()


def activation_history():
    connection = get_connection(); cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('''SELECT a.*,v.version_number,v.policy_name,
            LEAD(a.effective_from) OVER (ORDER BY a.effective_from) AS effective_to
            FROM payroll_policy_activations a JOIN payroll_policy_versions v USING(policy_version_id)
            ORDER BY a.effective_from''')
        return cursor.fetchall()
    finally:
        cursor.close(); connection.close()


def _transaction(operation):
    connection = get_connection(); cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        lock_payroll_inputs(cursor)
        result = operation(cursor)
        connection.commit()
        return result
    except Exception as error:
        connection.rollback()
        raise_payroll_lock_error(error)
        if getattr(error, 'errno', None) == 1062:
            raise ValueError('The policy version or activation date already exists. Reload and review the current policy.') from error
        raise
    finally:
        cursor.close(); connection.close()


def _lock_policy(cursor, policy_id):
    cursor.execute('SELECT * FROM payroll_policy_versions WHERE policy_version_id=%s FOR UPDATE', (policy_id,))
    row = _decode(cursor.fetchone())
    if not row:
        raise ValueError('Payroll policy was not found.')
    return row


def _draft_revision(row, revision):
    if row['status'] != 'DRAFT':
        raise ValueError('Only DRAFT policies may be edited or approved. Approved content is immutable.')
    if row['revision'] != revision:
        raise ValueError('This draft changed after the form was opened. Review the current version before submitting again.')
    positive_integer(revision+1, 'Next draft revision')


def _parameters(values):
    return tuple(json.dumps(values[name], separators=(',', ':')) if name in JSON_RULES else values[name] for name in CONFIG_FIELDS)


def create_policy(payload, actor_id):
    values = policy_values(payload)
    actor_id = positive_integer(actor_id, 'Acting user', 2147483647)
    def write(cursor):
        cursor.execute('SELECT version_number FROM payroll_policy_versions ORDER BY version_number DESC LIMIT 1 FOR UPDATE')
        previous = cursor.fetchone()
        version = positive_integer((previous['version_number'] if previous else 0)+1, 'Policy version')
        cursor.execute('INSERT INTO payroll_policy_versions (version_number,'+','.join(CONFIG_FIELDS)+',created_by,updated_by) VALUES ('+
                       ','.join(['%s']*(len(CONFIG_FIELDS)+3))+')', (version,*_parameters(values),actor_id,actor_id))
        return _lock_policy(cursor, cursor.lastrowid)
    return _transaction(write)


def update_policy(policy_id, revision, payload, actor_id):
    policy_id = positive_integer(policy_id, 'Policy ID', 2147483647)
    revision = positive_integer(revision, 'Draft revision')
    actor_id = positive_integer(actor_id, 'Acting user', 2147483647)
    values = policy_values(payload)
    def write(cursor):
        row = _lock_policy(cursor, policy_id); _draft_revision(row, revision)
        if policy_values({name: row[name] for name in CONFIG_FIELDS}) == values:
            raise ValueError('No policy configuration changes were submitted.')
        cursor.execute('UPDATE payroll_policy_versions SET '+','.join(name+'=%s' for name in CONFIG_FIELDS)+
                       ',revision=revision+1,updated_by=%s WHERE policy_version_id=%s AND status=\'DRAFT\' AND revision=%s',
                       (*_parameters(values),actor_id,policy_id,revision))
        if cursor.rowcount != 1:
            raise ValueError('The draft changed concurrently. Reload and review it.')
        return _lock_policy(cursor, policy_id)
    return _transaction(write)


def approve_policy(policy_id, revision, reference, confirmed, actor_id):
    policy_id = positive_integer(policy_id, 'Policy ID', 2147483647)
    revision = positive_integer(revision, 'Draft revision')
    actor_id = positive_integer(actor_id, 'Acting user', 2147483647)
    reference = approval_reference(reference)
    if confirmed is not True:
        raise ValueError('Confirm that the required company approvals have been obtained before approving this policy.')
    def write(cursor):
        row = _lock_policy(cursor, policy_id); _draft_revision(row, revision)
        values = policy_values({name: row[name] for name in CONFIG_FIELDS}); require_resolved(values)
        row['approval_reference'] = reference
        digest = configuration_hash(row)
        cursor.execute('''UPDATE payroll_policy_versions SET status='APPROVED',revision=revision+1,
            updated_by=%s,approved_by=%s,approved_at=NOW(6),approval_reference=%s,configuration_hash=%s
            WHERE policy_version_id=%s AND status='DRAFT' AND revision=%s''',
            (actor_id,actor_id,reference,digest,policy_id,revision))
        if cursor.rowcount != 1: raise ValueError('The draft changed concurrently. Approval was not recorded.')
        return _lock_policy(cursor, policy_id)
    return _transaction(write)


def activate_policy(policy_id, actor_id, timezone_name):
    policy_id = positive_integer(policy_id, 'Policy ID', 2147483647)
    actor_id = positive_integer(actor_id, 'Acting user', 2147483647)
    def write(cursor):
        row = _lock_policy(cursor, policy_id)
        if row['status'] != 'APPROVED': raise ValueError('Only an APPROVED policy may be scheduled for activation.')
        require_resolved(policy_values({name: row[name] for name in CONFIG_FIELDS}))
        verify_configuration_hash(row)
        start = effective_date(row['effective_from'])
        # Read the company date after waiting for the guard, not from a stale form.
        if start <= company_today(timezone_name):
            raise ValueError('Activation must start on a future company-local date at a cutoff boundary.')
        cursor.execute('SELECT * FROM payroll_policy_activations ORDER BY effective_from DESC LIMIT 1 FOR UPDATE')
        latest = cursor.fetchone()
        if latest and start <= latest['effective_from']:
            raise ValueError('Activation already exists or conflicts with the chronological schedule. Backdating and insertion are not permitted.')
        cursor.execute('''SELECT payroll_period_id FROM payroll_periods
            WHERE policy_version_id IS NOT NULL AND status <> 'CANCELLED' AND end_date >= %s
            ORDER BY payroll_period_id LIMIT 1 FOR UPDATE''', (start,))
        if cursor.fetchone():
            raise ValueError('Activation would change the policy schedule for an existing non-cancelled payroll period. No references were changed.')
        if start <= company_today(timezone_name):
            raise ValueError('The company date changed while scheduling. Activation must still start on a future date.')
        cursor.execute('INSERT INTO payroll_policy_activations(effective_from,policy_version_id,activated_by) VALUES(%s,%s,%s)',
                       (start,policy_id,actor_id))
        return row
    return _transaction(write)
