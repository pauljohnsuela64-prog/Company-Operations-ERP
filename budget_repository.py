from finance_validation import budget_values, identifier, lock_department
# ==========================================================
# FINANCE - BUDGET REPOSITORY
# ==========================================================

from decimal import Decimal

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
    department_id, budget_year, budget_amount, notes = budget_values(
        department_id, budget_year, budget_amount, notes)
    created_by = identifier(created_by, 'Creator')
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        lock_department(cursor, department_id)


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

    except Exception as error:
        connection.rollback()
        if getattr(error, 'errno', None) == 1062:
            raise ValueError('This department already has a budget for the selected year.') from error
        if getattr(error, 'errno', None) in (1205, 1213):
            raise ValueError('Finance data changed concurrently. Reload and try again.') from error
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
    department_id, budget_year, budget_amount, notes = budget_values(
        department_id, budget_year, budget_amount, notes)
    budget_id = identifier(budget_id, 'Budget')
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

        lock_department(cursor, department_id)
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


    except Exception as error:
        connection.rollback()
        if getattr(error, 'errno', None) == 1062:
            raise ValueError('This department already has a budget for the selected year.') from error
        if getattr(error, 'errno', None) in (1205, 1213):
            raise ValueError('Finance data changed concurrently. Reload and try again.') from error
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


# ==========================================================
# GET PAID EXPENSES FOR DEPARTMENT BUDGET
#
# Uses the budget's:
# - Department
# - Budget Year
#
# Only PAID expenses count as actual spending.
# ==========================================================

def get_paid_expenses_for_budget(budget_id, connection=None):
    owns_connection = connection is None
    if owns_connection:
        connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                e.expense_id,
                e.expense_number,
                e.expense_date,

                e.category_id,
                ec.category_code,
                ec.category_name,

                e.description,
                e.amount,
                e.reference_number,
                e.payment_method,
                e.status,

                e.supplier_id,
                s.supplier_name,

                e.purchase_order_id,
                po.po_number

            FROM department_budgets b

            INNER JOIN expenses e
                ON e.department_id = b.department_id

                AND YEAR(e.expense_date)
                    = b.budget_year

                AND e.status = 'PAID'

            INNER JOIN expense_categories ec
                ON e.category_id = ec.category_id

            LEFT JOIN suppliers s
                ON e.supplier_id = s.supplier_id

            LEFT JOIN purchase_orders po
                ON e.purchase_order_id
                    = po.purchase_order_id

            WHERE b.budget_id = %s

            ORDER BY
                e.expense_date DESC,
                e.expense_id DESC
            """,
            (budget_id,),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        if owns_connection:
            connection.close()


# ==========================================================
# GET DEPARTMENT BUDGET DETAILS BY ID
#
# Returns:
# - Department
# - Budget year
# - Budget amount
# - Paid spending
# - Remaining amount
# ==========================================================

def get_department_budget_details_by_id(budget_id, connection=None):
    owns_connection = connection is None
    if owns_connection:
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

            WHERE b.budget_id = %s

            LIMIT 1
            """,
            (budget_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        if owns_connection:
            connection.close()

# ==========================================================
# CHECK EXPENSE AGAINST DEPARTMENT BUDGET
#
# Used before an APPROVED expense is marked as PAID.
#
# Checks:
# - Expense department
# - Expense year
# - Department budget
# - Current paid spending
# - Projected spending
# - Possible overspending
# ==========================================================

def check_expense_against_budget(expense_id):
    """Advisory display only; payment revalidates under its own transaction locks."""
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # GET EXPENSE + MATCHING DEPARTMENT BUDGET
        # ==========================================================

        cursor.execute(
            """
            SELECT
                e.expense_id,
                e.expense_number,
                e.expense_date,
                e.amount AS expense_amount,
                e.status,

                e.department_id,
                d.department_name,

                YEAR(e.expense_date) AS budget_year,

                b.budget_id,
                b.budget_amount,

                COALESCE(
                    (
                        SELECT SUM(paid_expense.amount)

                        FROM expenses paid_expense

                        WHERE
                            paid_expense.department_id
                                = e.department_id

                            AND YEAR(
                                paid_expense.expense_date
                            ) = YEAR(e.expense_date)

                            AND paid_expense.status = 'PAID'
                    ),
                    0
                ) AS spent_amount

            FROM expenses e

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            LEFT JOIN department_budgets b
                ON b.department_id = e.department_id
                AND b.budget_year = YEAR(e.expense_date)

            WHERE e.expense_id = %s

            LIMIT 1
            """,
            (expense_id,),
        )

        expense = cursor.fetchone()


        # ==================================================
        # EXPENSE VALIDATION
        # ==========================================================

        if not expense:
            raise ValueError(
                "Expense was not found."
            )

        if expense["status"] != "APPROVED":
            raise ValueError(
                "Only approved expenses can be checked "
                "for payment."
            )


        # ==================================================
        # NO DEPARTMENT
        #
        # Budget control cannot be applied when the
        # expense is not assigned to a department.
        # ==========================================================

        if expense["department_id"] is None:

            return {
                "expense_id": expense["expense_id"],
                "expense_number": expense["expense_number"],
                "department_id": None,
                "department_name": None,
                "budget_year": expense["budget_year"],

                "budget_found": False,
                "budget_required": False,

                "budget_amount": None,
                "spent_amount": Decimal("0.00"),
                "expense_amount": expense["expense_amount"],
                "projected_spent": None,
                "remaining_before": None,
                "remaining_after": None,
                "over_by": Decimal("0.00"),

                "can_pay": True,
            }


        # ==================================================
        # NO DEPARTMENT BUDGET
        # ==========================================================

        if expense["budget_id"] is None:

            return {
                "expense_id": expense["expense_id"],
                "expense_number": expense["expense_number"],
                "department_id": expense["department_id"],
                "department_name": expense["department_name"],
                "budget_year": expense["budget_year"],

                "budget_found": False,
                "budget_required": True,

                "budget_amount": None,
                "spent_amount": expense["spent_amount"],
                "expense_amount": expense["expense_amount"],
                "projected_spent": None,
                "remaining_before": None,
                "remaining_after": None,
                "over_by": Decimal("0.00"),

                "can_pay": False,
            }


        # ==================================================
        # CALCULATE PROJECTED BUDGET USAGE
        # ==========================================================

        budget_amount = expense["budget_amount"]

        spent_amount = expense["spent_amount"]

        expense_amount = expense["expense_amount"]

        projected_spent = (
            spent_amount
            + expense_amount
        )

        remaining_before = (
            budget_amount
            - spent_amount
        )

        remaining_after = (
            budget_amount
            - projected_spent
        )


        # ==================================================
        # CHECK FOR OVERSPENDING
        # ==========================================================

        if projected_spent > budget_amount:

            over_by = (
                projected_spent
                - budget_amount
            )

            can_pay = False

        else:

            over_by = Decimal("0.00")

            can_pay = True


        # ==================================================
        # RETURN BUDGET CHECK
        # ==========================================================

        return {
            "expense_id": expense["expense_id"],
            "expense_number": expense["expense_number"],

            "department_id": expense["department_id"],
            "department_name": expense["department_name"],

            "budget_year": expense["budget_year"],

            "budget_found": True,
            "budget_required": True,

            "budget_amount": budget_amount,
            "spent_amount": spent_amount,
            "expense_amount": expense_amount,

            "projected_spent": projected_spent,

            "remaining_before": remaining_before,
            "remaining_after": remaining_after,

            "over_by": over_by,

            "can_pay": can_pay,
        }

    finally:

        cursor.close()
        connection.close()

def get_department_budget_report(budget_id):
    """Budget totals and paid detail rows from the same read-only snapshot."""
    connection = get_connection()
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ', consistent_snapshot=True, readonly=True)
        budget = get_department_budget_details_by_id(budget_id, connection=connection)
        records = get_paid_expenses_for_budget(budget_id, connection=connection) if budget else []
        connection.commit()
        return budget, records
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
