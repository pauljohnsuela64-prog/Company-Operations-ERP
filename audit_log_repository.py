# ==========================================================
# AUDIT LOG REPOSITORY
# ==========================================================

from database import get_connection


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

def get_filtered_audit_logs(
    search_text=None,
    module=None,
    action=None,
    start_date=None,
    end_date=None,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        query = """
            SELECT
                audit_log_id,
                user_id,
                username,
                module,
                action,
                entity_type,
                entity_id,
                description,
                created_at

            FROM audit_logs

            WHERE 1 = 1
        """


        parameters = []


        # ==================================================
        # SEARCH
        # ==========================================================

        if search_text:

            search_value = (
                f"%{search_text}%"
            )

            query += """
                AND (
                    username LIKE %s
                    OR module LIKE %s
                    OR action LIKE %s
                    OR entity_type LIKE %s
                    OR entity_id LIKE %s
                    OR description LIKE %s
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
                ]
            )


        # ==================================================
        # MODULE
        # ==========================================================

        if module:

            query += """
                AND module = %s
            """

            parameters.append(
                module
            )


        # ==================================================
        # ACTION
        # ==========================================================

        if action:

            query += """
                AND action = %s
            """

            parameters.append(
                action
            )


        # ==================================================
        # START DATE
        # ==========================================================

        if start_date:

            query += """
                AND created_at >= %s
            """

            parameters.append(
                start_date
            )


        # ==================================================
        # END DATE
        # ==========================================================

        if end_date:

            query += """
                AND created_at
                    < DATE_ADD(
                        %s,
                        INTERVAL 1 DAY
                    )
            """

            parameters.append(
                end_date
            )


        # ==================================================
        # ORDER
        # ==========================================================

        query += """
            ORDER BY
                created_at DESC,
                audit_log_id DESC

            LIMIT 500
        """


        cursor.execute(
            query,
            tuple(parameters),
        )


        return cursor.fetchall()


    finally:

        cursor.close()
        connection.close()