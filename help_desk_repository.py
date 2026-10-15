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
    changed_by,
):
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
        # UPDATE TECHNICIAN
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


        # ==================================================
        # HISTORY
        # ==========================================================

        cursor.execute(
            """
            INSERT INTO helpdesk_ticket_history (
                ticket_id,
                action_type,
                old_status,
                new_status,
                details,
                changed_by
            )
            VALUES (
                %s,
                'ASSIGNED',
                %s,
                %s,
                'Technician assigned or reassigned',
                %s
            )
            """,
            (
                ticket_id,
                ticket["status"],
                ticket["status"],
                changed_by,
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

def start_helpdesk_ticket(
    ticket_id,
    changed_by,
):
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




        cursor.execute(
            """
            UPDATE helpdesk_tickets

            SET status = 'IN_PROGRESS'

            WHERE ticket_id = %s
            """,
            (ticket_id,),
        )

        cursor.execute(
            """
            INSERT INTO helpdesk_ticket_history (
                ticket_id,
                action_type,
                old_status,
                new_status,
                details,
                changed_by
            )
            VALUES (
                %s,
                'STATUS_CHANGE',
                'OPEN',
                'IN_PROGRESS',
                'Work started on ticket',
                %s
            )
            """,
            (
                ticket_id,
                changed_by,
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
# RESOLVE HELP DESK TICKET
# ==========================================================

def resolve_helpdesk_ticket(
    ticket_id,
    resolution,
    changed_by,
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

        cursor.execute(
            """
            INSERT INTO helpdesk_ticket_history (
                ticket_id,
                action_type,
                old_status,
                new_status,
                details,
                changed_by
            )
            VALUES (
                %s,
                'RESOLVED',
                'IN_PROGRESS',
                'RESOLVED',
                %s,
                %s
            )
            """,
            (
                ticket_id,
                resolution[:255],
                changed_by,
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

def close_helpdesk_ticket(
    ticket_id,
    changed_by,
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

        if ticket["status"] != "RESOLVED":

            raise ValueError(
                "Only resolved tickets can be closed."
            )




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

        cursor.execute(
            """
            INSERT INTO helpdesk_ticket_history (
                ticket_id,
                action_type,
                old_status,
                new_status,
                details,
                changed_by
            )
            VALUES (
                %s,
                'STATUS_CHANGE',
                'RESOLVED',
                'CLOSED',
                'Ticket closed',
                %s
            )
            """,
            (
                ticket_id,
                changed_by,
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