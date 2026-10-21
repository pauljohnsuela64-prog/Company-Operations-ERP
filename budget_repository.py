from finance_validation import budget_values, identifier, lock_department
from budget_management import BudgetError, listing_values
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

BUDGET_LIST_BASE = """
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


def get_all_department_budgets(year=None):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # BASE QUERY
        # ==========================================================

        query = BUDGET_LIST_BASE

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

def _require_budget_storage(cursor,include_expenses=False):
    """The global schema manifest does not cover Finance tables. Never repair them."""
    cursor.execute("SELECT TABLE_NAME,ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('department_budgets','expenses')")
    rows=cursor.fetchall()
    engines={row['TABLE_NAME'] if isinstance(row,dict) else row[0]:row['ENGINE'] if isinstance(row,dict) else row[1] for row in rows}
    required=('department_budgets','expenses') if include_expenses else ('department_budgets',)
    if any(engines.get(name)!='InnoDB' for name in required):
        raise BudgetError('Budget storage is temporarily unavailable. Ask an administrator to verify the Finance schema.',503)


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
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        _require_budget_storage(cursor)
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

        budget_id = cursor.lastrowid
        connection.commit()

        return budget_id

    except Exception as error:
        connection.rollback()
        if getattr(error, 'errno', None) == 1062:
            raise ValueError('This department already has a budget for the selected year.') from error
        if getattr(error, 'errno', None) in (1205, 1213):
            raise ValueError('Finance data changed concurrently. Reload and try again.') from error
        raise

    finally:

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()



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
    budget_id = identifier(budget_id, 'Budget')
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


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
    cursor = None

    try:

        # ==================================================
        # START TRANSACTION
        # ==========================================================

        connection.start_transaction()
        cursor = connection.cursor()
        _require_budget_storage(cursor)


        # ==================================================
        # LOCK EXISTING BUDGET
        # ==========================================================

        cursor.execute(
            """
            SELECT budget_id,department_id,budget_year,budget_amount,notes
            FROM department_budgets
            WHERE budget_id = %s
            FOR UPDATE
            """,
            (budget_id,),
        )

        existing_budget = cursor.fetchone()

        if not existing_budget:
            raise BudgetError('Department budget was not found.',404)


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        lock_department(cursor, department_id)
        if tuple(existing_budget[1:]) == (department_id,budget_year,budget_amount,notes):
            connection.rollback()
            return False
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
        return True


    except Exception as error:
        connection.rollback()
        if getattr(error, 'errno', None) == 1062:
            raise ValueError('This department already has a budget for the selected year.') from error
        if getattr(error, 'errno', None) in (1205, 1213):
            raise ValueError('Finance data changed concurrently. Reload and try again.') from error
        raise

    finally:

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


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



def get_department_budget_page(args,default_year):
    selected=listing_values(args,default_year)
    params=[selected['year']]
    query=BUDGET_LIST_BASE+' AND b.budget_year=%s'
    if selected['department_id']=='none':query+=' AND b.department_id IS NULL'
    elif selected['department_id'] is not None:
        query+=' AND b.department_id=%s';params.append(selected['department_id'])
    if selected['search']:
        needle='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        query+=" AND (d.department_code LIKE %s ESCAPE '!' OR d.department_name LIKE %s ESCAPE '!')"
        params.extend([needle,needle])
    connection=get_connection();cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        _require_budget_storage(cursor,include_expenses=True)
        cursor.execute('SELECT COUNT(*) AS department_count,COALESCE(SUM(budget_amount),0) AS total_budget,'
            'COALESCE(SUM(spent_amount),0) AS total_spent,COALESCE(SUM(remaining_amount),0) AS total_remaining FROM ('+query+') filtered_budgets',tuple(params))
        summary=cursor.fetchone();total=summary['department_count']
        pages=max(1,(total+selected['page_size']-1)//selected['page_size'])
        selected['page']=min(selected['page'],pages)
        cursor.execute(query+' ORDER BY b.budget_year DESC,d.department_name ASC,b.budget_id ASC LIMIT %s OFFSET %s',
            (*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        rows=cursor.fetchall();first=(selected['page']-1)*selected['page_size']+1 if total else 0
        return dict(records=rows,summary=summary,total=total,pages=pages,filters=selected,first=first,last=first+len(rows)-1 if rows else 0)
    finally:
        try:connection.rollback()
        finally:
            try:
                if cursor is not None:cursor.close()
            finally:connection.close()
