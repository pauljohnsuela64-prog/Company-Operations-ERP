# ==========================================================
# ATTENDANCE REPOSITORY
# ==========================================================

from database import get_connection


# ==========================================================
# GET ALL ATTENDANCE RECORDS
# ==========================================================

def get_all_attendance_records():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                a.attendance_id,
                a.employee_id,
                a.attendance_date,
                a.time_in,
                a.time_out,
                a.status,
                a.notes,
                a.created_by,
                a.updated_by,
                a.created_at,
                a.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name,

                creator.username
                    AS created_by_username,

                updater.username
                    AS updated_by_username

            FROM attendance_records a

            INNER JOIN employees e
                ON a.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            INNER JOIN users creator
                ON a.created_by = creator.user_id

            LEFT JOIN users updater
                ON a.updated_by = updater.user_id

            ORDER BY
                a.attendance_date DESC,
                e.last_name,
                e.first_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ATTENDANCE RECORD BY ID
# ==========================================================

def get_attendance_record_by_id(
    attendance_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                a.attendance_id,
                a.employee_id,
                a.attendance_date,
                a.time_in,
                a.time_out,
                a.status,
                a.notes,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name

            FROM attendance_records a

            INNER JOIN employees e
                ON a.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            WHERE a.attendance_id = %s
            """,
            (
                attendance_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE ATTENDANCE RECORD
# ==========================================================

def create_attendance_record(
    employee_id,
    attendance_date,
    time_in,
    time_out,
    status,
    notes,
    created_by,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO attendance_records (
                employee_id,
                attendance_date,
                time_in,
                time_out,
                status,
                notes,
                created_by
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
                employee_id,
                attendance_date,
                time_in,
                time_out,
                status,
                notes,
                created_by,
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
# UPDATE ATTENDANCE RECORD
# ==========================================================

def update_attendance_record(
    attendance_id,
    employee_id,
    attendance_date,
    time_in,
    time_out,
    status,
    notes,
    updated_by,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE attendance_records

            SET
                employee_id = %s,
                attendance_date = %s,
                time_in = %s,
                time_out = %s,
                status = %s,
                notes = %s,
                updated_by = %s

            WHERE attendance_id = %s
            """,
            (
                employee_id,
                attendance_date,
                time_in,
                time_out,
                status,
                notes,
                updated_by,
                attendance_id,
            ),
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()