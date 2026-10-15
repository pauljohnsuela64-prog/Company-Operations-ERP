# ==========================================================
# IT MANAGEMENT - HELP DESK REPOSITORY
# ==========================================================

import uuid

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
# CREATE TICKET
# ==========================================================

def create_helpdesk_ticket(
    employee_id,
    department_id,
    category_id,
    subject,
    description,
    priority,
    created_by,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        connection.start_transaction()


        # ==================================================
        # TEMPORARY UNIQUE NUMBER
        # ==========================================================

        temporary_number = (
            "TMP-"
            + uuid.uuid4().hex
        )


        # ==================================================
        # CREATE TICKET
        # ==========================================================

        cursor.execute(
            """
            INSERT INTO helpdesk_tickets (
                ticket_number,
                employee_id,
                department_id,
                category_id,
                subject,
                description,
                priority,
                status,
                created_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'OPEN',
                %s
            )
            """,
            (
                temporary_number,
                employee_id,
                department_id,
                category_id,
                subject,
                description,
                priority,
                created_by,
            ),
        )

        ticket_id = cursor.lastrowid


        # ==================================================
        # FINAL TICKET NUMBER
        # ==========================================================

        ticket_number = (
            f"HD-{ticket_id:06d}"
        )

        cursor.execute(
            """
            UPDATE helpdesk_tickets

            SET ticket_number = %s

            WHERE ticket_id = %s
            """,
            (
                ticket_number,
                ticket_id,
            ),
        )


        connection.commit()

        return (
            ticket_id,
            ticket_number,
        )

    except Exception:

        connection.rollback()
        raise

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
# ASSIGN HELP DESK TICKET
# ==========================================================

def assign_helpdesk_ticket(
    ticket_id,
    assigned_to,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        # ==================================================
        # LOCK TICKET
        # ==========================================================

        cursor.execute(
            """
            SELECT
                ticket_id,
                status

            FROM helpdesk_tickets

            WHERE ticket_id = %s

            FOR UPDATE
            """,
            (ticket_id,),
        )

        ticket = cursor.fetchone()

        if not ticket:

            raise ValueError(
                "Help desk ticket was not found."
            )

        if ticket["status"] in (
            "RESOLVED",
            "CLOSED",
            "CANCELLED",
        ):

            raise ValueError(
                "Resolved, closed, or cancelled tickets "
                "cannot be assigned."
            )


        # ==================================================
        # UPDATE ASSIGNMENT
        # ==========================================================

        cursor.execute(
            """
            UPDATE helpdesk_tickets

            SET assigned_to = %s

            WHERE ticket_id = %s
            """,
            (
                assigned_to,
                ticket_id,
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
# START HELP DESK TICKET
# ==========================================================

def start_helpdesk_ticket(ticket_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                ticket_id,
                status,
                assigned_to

            FROM helpdesk_tickets

            WHERE ticket_id = %s

            FOR UPDATE
            """,
            (ticket_id,),
        )

        ticket = cursor.fetchone()

        if not ticket:

            raise ValueError(
                "Help desk ticket was not found."
            )

        if ticket["status"] != "OPEN":

            raise ValueError(
                "Only open tickets can be started."
            )

        if ticket["assigned_to"] is None:

            raise ValueError(
                "Assign a technician before starting work."
            )


        # ==================================================
        # OPEN -> IN PROGRESS
        # ==========================================================

        cursor.execute(
            """
            UPDATE helpdesk_tickets

            SET status = 'IN_PROGRESS'

            WHERE ticket_id = %s
            """,
            (ticket_id,),
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# RESOLVE HELP DESK TICKET
# ==========================================================

def resolve_helpdesk_ticket(
    ticket_id,
    resolution,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                ticket_id,
                status

            FROM helpdesk_tickets

            WHERE ticket_id = %s

            FOR UPDATE
            """,
            (ticket_id,),
        )

        ticket = cursor.fetchone()

        if not ticket:

            raise ValueError(
                "Help desk ticket was not found."
            )

        if ticket["status"] != "IN_PROGRESS":

            raise ValueError(
                "Only tickets in progress can be resolved."
            )


        # ==================================================
        # IN PROGRESS -> RESOLVED
        # ==========================================================

        cursor.execute(
            """
            UPDATE helpdesk_tickets

            SET
                status = 'RESOLVED',
                resolution = %s,
                resolved_at = CURRENT_TIMESTAMP

            WHERE ticket_id = %s
            """,
            (
                resolution,
                ticket_id,
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
# CLOSE HELP DESK TICKET
# ==========================================================

def close_helpdesk_ticket(ticket_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                ticket_id,
                status

            FROM helpdesk_tickets

            WHERE ticket_id = %s

            FOR UPDATE
            """,
            (ticket_id,),
        )

        ticket = cursor.fetchone()

        if not ticket:

            raise ValueError(
                "Help desk ticket was not found."
            )

        if ticket["status"] != "RESOLVED":

            raise ValueError(
                "Only resolved tickets can be closed."
            )


        # ==================================================
        # RESOLVED -> CLOSED
        # ==========================================================

        cursor.execute(
            """
            UPDATE helpdesk_tickets

            SET
                status = 'CLOSED',
                closed_at = CURRENT_TIMESTAMP

            WHERE ticket_id = %s
            """,
            (ticket_id,),
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()