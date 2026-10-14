# ==========================================================
# FINANCE - BUDGET REPOSITORY
# ==========================================================

from database import get_connection


# ==========================================================
# GET ALL DEPARTMENT BUDGETS
#
# Also calculates:
# - Paid expenses
# - Remaining budget
# ==========================================================

# ==========================================================
# GET DEPARTMENT BUDGETS
#
# Optional filter:
# - Budget Year
#
# Also calculates:
# - Paid expenses
# - Remaining budget
# ==========================================================

def get_all_department_budgets(year=None):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # BASE QUERY
        # ==========================================================

        query = """
            SELECT
                b.budget_id,
                b.department_id,
                d.department_name,

                b.budget_year,
                b.budget_amount,
                b.notes,

                b.created_by,
                u.username AS created_by_username,

                b.created_at,
                b.updated_at,

                COALESCE(
                    expense_totals.spent_amount,
                    0
                ) AS spent_amount,

                (
                    b.budget_amount
                    -
                    COALESCE(
                        expense_totals.spent_amount,
                        0
                    )
                ) AS remaining_amount

            FROM department_budgets b

            INNER JOIN departments d
                ON b.department_id = d.department_id

            INNER JOIN users u
                ON b.created_by = u.user_id

            LEFT JOIN (
                SELECT
                    department_id,
                    YEAR(expense_date) AS expense_year,
                    SUM(amount) AS spent_amount

                FROM expenses

                WHERE
                    status = 'PAID'
                    AND department_id IS NOT NULL

                GROUP BY
                    department_id,
                    YEAR(expense_date)

            ) expense_totals

                ON expense_totals.department_id
                    = b.department_id

                AND expense_totals.expense_year
                    = b.budget_year

            WHERE 1 = 1
        """

        parameters = []


        # ==================================================
        # YEAR FILTER
        # ==========================================================

        if year is not None:

            query += """
                AND b.budget_year = %s
            """

            parameters.append(year)


        # ==================================================
        # SORTING
        # ==========================================================

        query += """
            ORDER BY
                b.budget_year DESC,
                d.department_name ASC
        """


        # ==================================================
        # EXECUTE QUERY
        # ==========================================================

        cursor.execute(
            query,
            tuple(parameters),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE DEPARTMENT BUDGET
#
# Creates one budget for a department and year.
# Duplicate department/year combinations are blocked
# by the database UNIQUE constraint.
# ==========================================================

def create_department_budget(
    department_id,
    budget_year,
    budget_amount,
    notes,
    created_by,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ==================================================
        # DATABASE INSERT
        # ==========================================================

        cursor.execute(
            """
            INSERT INTO department_budgets (
                department_id,
                budget_year,
                budget_amount,
                notes,
                created_by
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                department_id,
                budget_year,
                budget_amount,
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
# GET BUDGET BY DEPARTMENT AND YEAR
#
# Used to prevent duplicate budgets such as:
# IT Department + 2026
# ==========================================================

def get_department_budget_by_department_and_year(
    department_id,
    budget_year,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                budget_id,
                department_id,
                budget_year,
                budget_amount,
                notes,
                created_by,
                created_at,
                updated_at

            FROM department_budgets

            WHERE
                department_id = %s
                AND budget_year = %s

            LIMIT 1
            """,
            (
                department_id,
                budget_year,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()



# ==========================================================
# GET DEPARTMENT BUDGET BY ID
#
# Used by the Edit Budget page.
# ==========================================================

def get_department_budget_by_id(budget_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                b.budget_id,
                b.department_id,
                d.department_name,
                b.budget_year,
                b.budget_amount,
                b.notes,
                b.created_by,
                u.username AS created_by_username,
                b.created_at,
                b.updated_at

            FROM department_budgets b

            INNER JOIN departments d
                ON b.department_id = d.department_id

            INNER JOIN users u
                ON b.created_by = u.user_id

            WHERE b.budget_id = %s

            LIMIT 1
            """,
            (budget_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# UPDATE DEPARTMENT BUDGET
#
# Updates:
# - Department
# - Budget Year
# - Budget Amount
# - Notes
# ==========================================================

def update_department_budget(
    budget_id,
    department_id,
    budget_year,
    budget_amount,
    notes,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ==================================================
        # START TRANSACTION
        # ==========================================================

        connection.start_transaction()


        # ==================================================
        # LOCK EXISTING BUDGET
        # ==========================================================

        cursor.execute(
            """
            SELECT budget_id
            FROM department_budgets
            WHERE budget_id = %s
            FOR UPDATE
            """,
            (budget_id,),
        )

        existing_budget = cursor.fetchone()

        if not existing_budget:
            raise ValueError(
                "Department budget was not found."
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        cursor.execute(
            """
            UPDATE department_budgets

            SET
                department_id = %s,
                budget_year = %s,
                budget_amount = %s,
                notes = %s

            WHERE budget_id = %s
            """,
            (
                department_id,
                budget_year,
                budget_amount,
                notes,
                budget_id,
            ),
        )


        # ==================================================
        # SAVE CHANGES
        # ==========================================================

        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET BUDGET SUMMARY BY YEAR
#
# Calculates:
# - Number of department budgets
# - Total budget
# - Total spent
# - Total remaining
# ==========================================================

def get_budget_summary(year):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT

                COUNT(*) AS department_count,

                COALESCE(
                    SUM(b.budget_amount),
                    0
                ) AS total_budget,

                COALESCE(
                    SUM(
                        COALESCE(
                            expense_totals.spent_amount,
                            0
                        )
                    ),
                    0
                ) AS total_spent,

                COALESCE(
                    SUM(
                        b.budget_amount
                        -
                        COALESCE(
                            expense_totals.spent_amount,
                            0
                        )
                    ),
                    0
                ) AS total_remaining

            FROM department_budgets b

            LEFT JOIN (
                SELECT
                    department_id,
                    YEAR(expense_date) AS expense_year,
                    SUM(amount) AS spent_amount

                FROM expenses

                WHERE
                    status = 'PAID'
                    AND department_id IS NOT NULL

                GROUP BY
                    department_id,
                    YEAR(expense_date)

            ) expense_totals

                ON expense_totals.department_id
                    = b.department_id

                AND expense_totals.expense_year
                    = b.budget_year

            WHERE b.budget_year = %s
            """,
            (year,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()