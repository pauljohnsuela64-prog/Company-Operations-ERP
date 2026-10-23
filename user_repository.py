from dataclasses import dataclass
import re
import mysql.connector
from database import get_connection


class AdminIntegrityError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AdminAccessResult:
    user_id: int
    username: str
    changed: bool


def _admin_identifier(value, label):
    raw = str(value).strip()
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,10}', raw) or not 1 <= int(raw) <= 2147483647:
        raise AdminIntegrityError(f'Invalid {label}.')
    return int(raw)


def _write_user_access(user_id, actor_user_id, *, role_id=None, is_active=None):
    user_id = _admin_identifier(user_id, 'user')
    actor_user_id = _admin_identifier(actor_user_id, 'acting user')
    if role_id is not None:
        role_id = _admin_identifier(role_id, 'role')
    if user_id == actor_user_id:
        raise AdminIntegrityError('You cannot change your own role or account status.')
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction(isolation_level='READ COMMITTED')
        cursor = connection.cursor(dictionary=True)
        # Stable existing permission row serializes both access writers without
        # exclusively locking a role needed by user->role readers (Help Desk).
        # Only lock it; never create permissions or change any grants here.
        cursor.execute("SELECT permission_id FROM permissions WHERE permission_code='users.manage' FOR UPDATE")
        guardian = cursor.fetchone()
        if not guardian:
            raise AdminIntegrityError('Administration integrity is unavailable. Contact an operator.', 503)
        cursor.execute("SELECT role_id FROM roles WHERE role_name='Super Admin' FOR SHARE")
        super_role = cursor.fetchone()
        if not super_role:
            raise AdminIntegrityError('Administration integrity is unavailable. Contact an operator.', 503)
        super_role_id = super_role['role_id']
        cursor.execute('SELECT user_id,username,role_id,is_active FROM users WHERE user_id=%s FOR UPDATE', (user_id,))
        current = cursor.fetchone()
        if current is None:
            raise AdminIntegrityError('User account not found.', 404)
        if role_id is not None:
            cursor.execute('SELECT role_id FROM roles WHERE role_id=%s FOR SHARE', (role_id,))
            if cursor.fetchone() is None:
                raise AdminIntegrityError('Selected role does not exist.')
        target_role = current['role_id'] if role_id is None else role_id
        target_active = bool(current['is_active']) if is_active is None else is_active
        changed = target_role != current['role_id'] or target_active != bool(current['is_active'])
        if not changed:
            connection.rollback()
            return AdminAccessResult(user_id, current['username'], False)
        if current['role_id'] == super_role_id and current['is_active'] and (target_role != super_role_id or not target_active):
            # Nonlocking READ COMMITTED read after the shared writer gate sees
            # preceding access commits, without locking other users out of order.
            cursor.execute('SELECT COUNT(*) AS total FROM users WHERE role_id=%s AND is_active=1', (super_role_id,))
            if cursor.fetchone()['total'] <= 1:
                raise AdminIntegrityError('You cannot remove or deactivate the last active Super Admin.', 409)
        cursor.execute('UPDATE users SET role_id=%s,is_active=%s WHERE user_id=%s', (target_role, target_active, user_id))
        if cursor.rowcount != 1:
            raise AdminIntegrityError('Account changed concurrently. Reload and review before retrying.', 409)
        connection.commit()
        return AdminAccessResult(user_id, current['username'], True)
    except Exception as error:
        try:
            connection.rollback()
        except mysql.connector.Error:
            pass
        if isinstance(error, mysql.connector.Error):
            if error.errno in (1205, 1213, 1452):
                raise AdminIntegrityError('Account data is busy or changed. Reload and review before retrying.', 409) from error
            raise AdminIntegrityError('Could not confirm the account change. Reload and reconcile before retrying.', 503) from error
        raise
    finally:
        failed = False
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
            raise AdminIntegrityError('Could not confirm the account change. Reload and reconcile before retrying.', 503)


def get_user_by_username(username):
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                u.user_id,
                u.username,
                u.password_hash,
                u.is_active,
                u.employee_id,
                r.role_id,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.username = %s
            LIMIT 1
            """,
            (username,),
        )

        return cursor.fetchone()

    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


def get_permissions_by_role_id(role_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT p.permission_code
            FROM permissions p
            JOIN role_permissions rp
                ON p.permission_id = rp.permission_id
            WHERE rp.role_id = %s
            ORDER BY p.permission_code
            """,
            (role_id,),
        )

        return [row[0] for row in cursor.fetchall()]

    finally:
        cursor.close()
        connection.close()


def update_last_login(user_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE users
            SET last_login_at = NOW()
            WHERE user_id = %s
            """,
            (user_id,),
        )

        connection.commit()

    finally:
        cursor.close()
        connection.close()

# ==========================================================
# USER ADMINISTRATION - GET ALL USERS
# ==========================================================

def get_all_users():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                u.user_id,
                u.employee_id,
                u.role_id,
                u.username,
                u.is_active,
                u.last_login_at,
                u.created_at,
                u.updated_at,

                r.role_name,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name

            FROM users u

            INNER JOIN roles r
                ON u.role_id = r.role_id

            LEFT JOIN employees e
                ON u.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            ORDER BY
                u.username
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# USER ADMINISTRATION - GET USER BY ID
# ==========================================================

def get_user_by_id(user_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                u.user_id,
                u.employee_id,
                u.role_id,
                u.username,
                u.password_hash,
                u.is_active,
                u.last_login_at,
                u.created_at,
                u.updated_at,

                r.role_name

            FROM users u

            INNER JOIN roles r
                ON u.role_id = r.role_id

            WHERE u.user_id = %s
            """,
            (user_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# USER ADMINISTRATION - GET ALL ROLES
# ==========================================================

def get_all_roles():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                role_id,
                role_name,
                description,
                created_at

            FROM roles

            ORDER BY
                role_id
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# USER ADMINISTRATION - GET AVAILABLE EMPLOYEES
#
# Only employees that do not already have a user account.
# ==========================================================

def get_available_user_employees():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,
                e.department_id,
                d.department_name

            FROM employees e

            LEFT JOIN users u
                ON e.employee_id = u.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            WHERE u.user_id IS NULL

            ORDER BY
                e.first_name,
                e.last_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# USER ADMINISTRATION - CREATE USER
# ==========================================================

def create_user(
    username,
    password_hash,
    role_id,
    employee_id=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users (
                employee_id,
                role_id,
                username,
                password_hash,
                is_active
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                1
            )
            """,
            (
                employee_id,
                role_id,
                username,
                password_hash,
            ),
        )

        connection.commit()

        return cursor.lastrowid

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# USER ADMINISTRATION - CHANGE ROLE
# ==========================================================

def update_user_role(user_id, role_id, *, actor_user_id):
    role_id = _admin_identifier(role_id, 'role')
    return _write_user_access(user_id, actor_user_id, role_id=role_id)


def set_user_active_status(user_id, is_active, *, actor_user_id):
    if type(is_active) is not bool:
        raise AdminIntegrityError('Account status must be active or inactive.')
    return _write_user_access(user_id, actor_user_id, is_active=is_active)


# ==========================================================
# USER ADMINISTRATION - COUNT ACTIVE SUPER ADMINS
# ==========================================================

def count_active_super_admins():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total

            FROM users u

            INNER JOIN roles r
                ON u.role_id = r.role_id

            WHERE
                r.role_name = 'Super Admin'
                AND u.is_active = 1
            """
        )

        result = cursor.fetchone()

        return result["total"]

    finally:

        cursor.close()
        connection.close()

# ==========================================================
# USER ADMINISTRATION - RESET PASSWORD
# ==========================================================

def update_user_password(
    user_id,
    password_hash,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (
                password_hash,
                user_id,
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
# ROLE ADMINISTRATION - GET ROLE BY ID
# ==========================================================

def get_role_by_id(role_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                role_id,
                role_name,
                description,
                created_at

            FROM roles

            WHERE role_id = %s
            """,
            (role_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# ROLE ADMINISTRATION - GET ALL PERMISSIONS
# ==========================================================

def get_all_permissions():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                permission_id,
                permission_code,
                description,
                created_at

            FROM permissions

            ORDER BY
                permission_code
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# ROLE ADMINISTRATION - GET ROLE PERMISSIONS
# ==========================================================

def get_role_permission_ids(role_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                permission_id

            FROM role_permissions

            WHERE role_id = %s
            """,
            (role_id,),
        )

        rows = cursor.fetchall()

        return {
            row["permission_id"]
            for row in rows
        }

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# ROLE ADMINISTRATION - UPDATE ROLE PERMISSIONS
# ==========================================================

def update_role_permissions(
    role_id,
    permission_ids,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ==================================================
        # REMOVE CURRENT PERMISSIONS
        # ==========================================================

        cursor.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id = %s
            """,
            (role_id,),
        )


        # ==================================================
        # ADD SELECTED PERMISSIONS
        # ==========================================================

        for permission_id in permission_ids:

            cursor.execute(
                """
                INSERT INTO role_permissions (
                    role_id,
                    permission_id
                )
                VALUES (
                    %s,
                    %s
                )
                """,
                (
                    role_id,
                    permission_id,
                ),
            )


        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()

def get_authorization_state(user_id):
    """One consistent query, including roles with no granted permissions."""
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT u.user_id, u.username, u.password_hash, u.is_active, u.role_id, r.role_name, p.permission_code "
            "FROM users u LEFT JOIN roles r ON r.role_id = u.role_id "
            "LEFT JOIN role_permissions rp ON rp.role_id = r.role_id "
            "LEFT JOIN permissions p ON p.permission_id = rp.permission_id "
            "WHERE u.user_id = %s", (user_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        user = {key: value for key, value in rows[0].items() if key != "permission_code"}
        user["permissions"] = frozenset(row["permission_code"] for row in rows if row["permission_code"] is not None)
        return user
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()
