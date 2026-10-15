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