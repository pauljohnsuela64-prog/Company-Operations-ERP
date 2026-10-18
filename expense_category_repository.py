from finance_validation import text, identifier
# ==========================================================
# EXPENSE CATEGORY REPOSITORY
#
# Handles database operations for Finance expense categories.
# ==========================================================

from database import get_connection


# ==========================================================
# GET ALL EXPENSE CATEGORIES
# ==========================================================

def get_all_expense_categories():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                category_id,
                category_code,
                category_name,
                description,
                is_active,
                created_at,
                updated_at
            FROM expense_categories
            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ACTIVE EXPENSE CATEGORIES
#
# Used later when creating an expense.
# ==========================================================

def get_active_expense_categories():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                category_id,
                category_code,
                category_name
            FROM expense_categories
            WHERE is_active = TRUE
            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ONE EXPENSE CATEGORY
# ==========================================================

def get_expense_category_by_id(category_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                category_id,
                category_code,
                category_name,
                description,
                is_active,
                created_at,
                updated_at
            FROM expense_categories
            WHERE category_id = %s
            LIMIT 1
            """,
            (category_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE EXPENSE CATEGORY
# ==========================================================

def create_expense_category(
    category_code,
    category_name,
    description=None,
):
    category_code = text(category_code, 'Category code', 30, True)
    category_name = text(category_name, 'Category name', 100, True)
    description = text(description, 'Description', 255)
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO expense_categories (
                category_code,
                category_name,
                description
            )
            VALUES (%s, %s, %s)
            """,
            (
                category_code,
                category_name,
                description,
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
# UPDATE EXPENSE CATEGORY
# ==========================================================

def update_expense_category(
    category_id,
    category_code,
    category_name,
    description=None,
):
    category_code = text(category_code, 'Category code', 30, True)
    category_name = text(category_name, 'Category name', 100, True)
    description = text(description, 'Description', 255)
    category_id = identifier(category_id, 'Category')
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE expense_categories
            SET
                category_code = %s,
                category_name = %s,
                description = %s
            WHERE category_id = %s
            """,
            (
                category_code,
                category_name,
                description,
                category_id,
            ),
        )

        connection.commit()

        return cursor.rowcount == 1

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# ACTIVATE / DEACTIVATE EXPENSE CATEGORY
# ==========================================================

def set_expense_category_active_status(
    category_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE expense_categories
            SET is_active = %s
            WHERE category_id = %s
            """,
            (
                is_active,
                category_id,
            ),
        )

        connection.commit()

        return cursor.rowcount == 1

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()