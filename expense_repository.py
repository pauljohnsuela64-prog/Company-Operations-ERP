# ==========================================================
# EXPENSE REPOSITORY
#
# Handles database operations for company expenses.
# ==========================================================

import uuid

from database import get_connection


# ==========================================================
# GET ALL EXPENSES
# ==========================================================

def get_all_expenses():
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

                e.department_id,
                d.department_name,

                e.supplier_id,
                s.supplier_name,

                e.purchase_order_id,
                po.po_number,

                e.description,
                e.amount,
                e.reference_number,
                e.payment_method,
                e.status,

                e.created_by,
                creator.username AS created_by_username,

                e.approved_by,
                approver.username AS approved_by_username,

                e.approved_at,
                e.paid_at,
                e.notes,
                e.created_at,
                e.updated_at

            FROM expenses e

            INNER JOIN expense_categories ec
                ON e.category_id = ec.category_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            LEFT JOIN suppliers s
                ON e.supplier_id = s.supplier_id

            LEFT JOIN purchase_orders po
                ON e.purchase_order_id = po.purchase_order_id

            INNER JOIN users creator
                ON e.created_by = creator.user_id

            LEFT JOIN users approver
                ON e.approved_by = approver.user_id

            ORDER BY
                e.expense_date DESC,
                e.expense_id DESC
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ONE EXPENSE
# ==========================================================

def get_expense_by_id(expense_id):
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

                e.department_id,
                d.department_name,

                e.supplier_id,
                s.supplier_name,

                e.purchase_order_id,
                po.po_number,

                e.description,
                e.amount,
                e.reference_number,
                e.payment_method,
                e.status,

                e.created_by,
                creator.username AS created_by_username,

                e.approved_by,
                approver.username AS approved_by_username,

                e.approved_at,
                e.paid_at,
                e.notes,
                e.created_at,
                e.updated_at

            FROM expenses e

            INNER JOIN expense_categories ec
                ON e.category_id = ec.category_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            LEFT JOIN suppliers s
                ON e.supplier_id = s.supplier_id

            LEFT JOIN purchase_orders po
                ON e.purchase_order_id = po.purchase_order_id

            INNER JOIN users creator
                ON e.created_by = creator.user_id

            LEFT JOIN users approver
                ON e.approved_by = approver.user_id

            WHERE e.expense_id = %s

            LIMIT 1
            """,
            (expense_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE EXPENSE
#
# New expenses begin with DRAFT status.
#
# The database ID is used to generate numbers such as:
#
# EXP-000001
# EXP-000002
# ==========================================================

def create_expense(
    expense_date,
    category_id,
    department_id,
    supplier_id,
    purchase_order_id,
    description,
    amount,
    reference_number,
    payment_method,
    created_by,
    notes,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ==================================================
        # START TRANSACTION
        # ==================================================

        connection.start_transaction()


        # ==================================================
        # TEMPORARY UNIQUE NUMBER
        #
        # We need a unique value before MySQL creates the
        # auto-increment expense_id.
        # ==================================================

        temporary_number = (
            "TEMP-"
            + uuid.uuid4().hex
        )


        # ==================================================
        # INSERT EXPENSE
        # ==================================================

        cursor.execute(
            """
            INSERT INTO expenses (
                expense_number,
                expense_date,
                category_id,
                department_id,
                supplier_id,
                purchase_order_id,
                description,
                amount,
                reference_number,
                payment_method,
                status,
                created_by,
                notes
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'DRAFT',
                %s,
                %s
            )
            """,
            (
                temporary_number,
                expense_date,
                category_id,
                department_id,
                supplier_id,
                purchase_order_id,
                description,
                amount,
                reference_number,
                payment_method,
                created_by,
                notes,
            ),
        )


        # ==================================================
        # GET GENERATED DATABASE ID
        # ==================================================

        expense_id = cursor.lastrowid


        # ==================================================
        # GENERATE EXPENSE NUMBER
        # ==================================================

        expense_number = (
            f"EXP-{expense_id:06d}"
        )


        # ==================================================
        # SAVE FINAL EXPENSE NUMBER
        # ==================================================

        cursor.execute(
            """
            UPDATE expenses
            SET expense_number = %s
            WHERE expense_id = %s
            """,
            (
                expense_number,
                expense_id,
            ),
        )


        # ==================================================
        # COMMIT TRANSACTION
        # ==================================================

        connection.commit()

        return expense_id, expense_number

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()



# ==========================================================
# APPROVE EXPENSE
#
# Changes:
# DRAFT -> APPROVED
#
# Stores who approved the expense and when.
# ==========================================================

def approve_expense(
    expense_id,
    approved_by,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # START TRANSACTION
        # ==================================================

        connection.start_transaction()


        # ==================================================
        # LOCK EXPENSE
        # ==================================================

        cursor.execute(
            """
            SELECT
                expense_id,
                expense_number,
                status
            FROM expenses
            WHERE expense_id = %s
            FOR UPDATE
            """,
            (expense_id,),
        )

        expense = cursor.fetchone()


        # ==================================================
        # VALIDATION
        # ==================================================

        if not expense:
            raise ValueError(
                "Expense not found."
            )

        if expense["status"] != "DRAFT":
            raise ValueError(
                "Only draft expenses can be approved."
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        cursor.execute(
            """
            UPDATE expenses
            SET
                status = 'APPROVED',
                approved_by = %s,
                approved_at = NOW()
            WHERE expense_id = %s
            """,
            (
                approved_by,
                expense_id,
            ),
        )


        # ==================================================
        # COMMIT
        # ==================================================

        connection.commit()

        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# MARK EXPENSE AS PAID
#
# Changes:
# APPROVED -> PAID
#
# Stores when the expense was paid.
# ==========================================================

def mark_expense_as_paid(expense_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # START TRANSACTION
        # ==================================================

        connection.start_transaction()


        # ==================================================
        # LOCK EXPENSE
        # ==================================================

        cursor.execute(
            """
            SELECT
                expense_id,
                expense_number,
                status
            FROM expenses
            WHERE expense_id = %s
            FOR UPDATE
            """,
            (expense_id,),
        )

        expense = cursor.fetchone()


        # ==================================================
        # VALIDATION
        # ==================================================

        if not expense:
            raise ValueError(
                "Expense not found."
            )

        if expense["status"] != "APPROVED":
            raise ValueError(
                "Only approved expenses can be marked as paid."
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        cursor.execute(
            """
            UPDATE expenses
            SET
                status = 'PAID',
                paid_at = NOW()
            WHERE expense_id = %s
            """,
            (expense_id,),
        )


        # ==================================================
        # COMMIT
        # ==================================================

        connection.commit()

        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()



# ==========================================================
# CANCEL EXPENSE
#
# Allowed:
# DRAFT -> CANCELLED
# APPROVED -> CANCELLED
#
# PAID expenses cannot be cancelled.
# ==========================================================

def cancel_expense(expense_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # START TRANSACTION
        # ==========================================================

        connection.start_transaction()


        # ==================================================
        # LOCK EXPENSE
        # ==========================================================

        cursor.execute(
            """
            SELECT
                expense_id,
                expense_number,
                status
            FROM expenses
            WHERE expense_id = %s
            FOR UPDATE
            """,
            (expense_id,),
        )

        expense = cursor.fetchone()


        # ==================================================
        # VALIDATION
        # ==========================================================

        if not expense:
            raise ValueError(
                "Expense not found."
            )

        if expense["status"] == "CANCELLED":
            raise ValueError(
                "Expense is already cancelled."
            )

        if expense["status"] == "PAID":
            raise ValueError(
                "Paid expenses cannot be cancelled."
            )

        if expense["status"] not in (
            "DRAFT",
            "APPROVED",
        ):
            raise ValueError(
                "This expense cannot be cancelled."
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        cursor.execute(
            """
            UPDATE expenses
            SET status = 'CANCELLED'
            WHERE expense_id = %s
            """,
            (expense_id,),
        )


        # ==================================================
        # COMMIT
        # ==========================================================

        connection.commit()

        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# UPDATE EXPENSE
#
# Only DRAFT expenses can be edited.
# ==========================================================

def update_expense(
    expense_id,
    expense_date,
    category_id,
    department_id,
    supplier_id,
    purchase_order_id,
    description,
    amount,
    reference_number,
    payment_method,
    notes,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # START TRANSACTION
        # ==================================================

        connection.start_transaction()


        # ==================================================
        # LOCK EXPENSE
        # ==================================================

        cursor.execute(
            """
            SELECT
                expense_id,
                status
            FROM expenses
            WHERE expense_id = %s
            FOR UPDATE
            """,
            (expense_id,),
        )

        expense = cursor.fetchone()


        # ==================================================
        # VALIDATION
        # ==================================================

        if not expense:
            raise ValueError(
                "Expense not found."
            )

        if expense["status"] != "DRAFT":
            raise ValueError(
                "Only draft expenses can be edited."
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        cursor.execute(
            """
            UPDATE expenses
            SET
                expense_date = %s,
                category_id = %s,
                department_id = %s,
                supplier_id = %s,
                purchase_order_id = %s,
                description = %s,
                amount = %s,
                reference_number = %s,
                payment_method = %s,
                notes = %s
            WHERE expense_id = %s
            """,
            (
                expense_date,
                category_id,
                department_id,
                supplier_id,
                purchase_order_id,
                description,
                amount,
                reference_number,
                payment_method,
                notes,
                expense_id,
            ),
        )


        # ==================================================
        # COMMIT
        # ==================================================

        connection.commit()

        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# FINANCE SUMMARY
#
# Returns counts and totals for expense statuses.
# ==========================================================

def get_finance_summary():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT

                COUNT(*) AS total_expenses,

                COALESCE(
                    SUM(amount),
                    0
                ) AS total_amount,

                SUM(
                    CASE
                        WHEN status = 'DRAFT'
                        THEN 1
                        ELSE 0
                    END
                ) AS draft_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'DRAFT'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS draft_amount,

                SUM(
                    CASE
                        WHEN status = 'APPROVED'
                        THEN 1
                        ELSE 0
                    END
                ) AS approved_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'APPROVED'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS approved_amount,

                SUM(
                    CASE
                        WHEN status = 'PAID'
                        THEN 1
                        ELSE 0
                    END
                ) AS paid_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'PAID'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS paid_amount,

                SUM(
                    CASE
                        WHEN status = 'CANCELLED'
                        THEN 1
                        ELSE 0
                    END
                ) AS cancelled_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'CANCELLED'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS cancelled_amount

            FROM expenses
            """
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# MONTHLY PAID EXPENSE SUMMARY
#
# Returns total PAID expenses grouped by month
# for a selected year.
# ==========================================================

def get_monthly_paid_expenses(year):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                MONTH(expense_date) AS month_number,
                MONTHNAME(expense_date) AS month_name,
                COUNT(*) AS expense_count,
                COALESCE(
                    SUM(amount),
                    0
                ) AS total_amount

            FROM expenses

            WHERE status = 'PAID'
              AND YEAR(expense_date) = %s

            GROUP BY
                MONTH(expense_date),
                MONTHNAME(expense_date)

            ORDER BY
                MONTH(expense_date)
            """,
            (year,),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# PAID EXPENSE CATEGORY BREAKDOWN
#
# Returns PAID expenses grouped by expense category
# for a selected year.
# ==========================================================

def get_paid_expenses_by_category(year):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                ec.category_id,
                ec.category_code,
                ec.category_name,

                COUNT(e.expense_id) AS expense_count,

                COALESCE(
                    SUM(e.amount),
                    0
                ) AS total_amount

            FROM expenses e

            INNER JOIN expense_categories ec
                ON e.category_id = ec.category_id

            WHERE e.status = 'PAID'
              AND YEAR(e.expense_date) = %s

            GROUP BY
                ec.category_id,
                ec.category_code,
                ec.category_name

            ORDER BY
                total_amount DESC,
                ec.category_name
            """,
            (year,),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()



# ==========================================================
# FINANCE SUMMARY BY YEAR
#
# Returns counts and totals for expense statuses
# for one selected year.
# ==========================================================

def get_finance_summary_by_year(year):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT

                COUNT(*) AS total_expenses,

                COALESCE(
                    SUM(amount),
                    0
                ) AS total_amount,

                SUM(
                    CASE
                        WHEN status = 'DRAFT'
                        THEN 1
                        ELSE 0
                    END
                ) AS draft_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'DRAFT'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS draft_amount,

                SUM(
                    CASE
                        WHEN status = 'APPROVED'
                        THEN 1
                        ELSE 0
                    END
                ) AS approved_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'APPROVED'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS approved_amount,

                SUM(
                    CASE
                        WHEN status = 'PAID'
                        THEN 1
                        ELSE 0
                    END
                ) AS paid_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'PAID'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS paid_amount,

                SUM(
                    CASE
                        WHEN status = 'CANCELLED'
                        THEN 1
                        ELSE 0
                    END
                ) AS cancelled_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'CANCELLED'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS cancelled_amount

            FROM expenses

            WHERE YEAR(expense_date) = %s
            """,
            (year,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()