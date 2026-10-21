from finance_validation import identifier
from expense_category_management import ExpenseCategoryError, fields, filters as category_filters
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
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


# ==========================================================
# GET ACTIVE EXPENSE CATEGORIES
#
# Used later when creating an expense.
# ==========================================================

def get_active_expense_categories():
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


# ==========================================================
# GET ONE EXPENSE CATEGORY
# ==========================================================

def get_expense_category_by_id(category_id):
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

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

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


# ==========================================================
# CREATE EXPENSE CATEGORY
# ==========================================================

def create_expense_category(
    category_code,
    category_name,
    description=None,
):
    category_code, category_name, description = fields(category_code,category_name,description)
    connection = get_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        _require_category_storage(cursor)

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

        category_id=cursor.lastrowid
        connection.commit()

        return category_id

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Expense category code already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise ExpenseCategoryError('Finance category data changed concurrently. Reload and try again.',409) from error
        raise

    finally:

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


# ==========================================================
# UPDATE EXPENSE CATEGORY
# ==========================================================

def update_expense_category(
    category_id,
    category_code,
    category_name,
    description=None,
):
    category_code, category_name, description = fields(category_code,category_name,description)
    category_id = identifier(category_id, 'Category')
    connection = get_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        _require_category_storage(cursor)
        cursor.execute('SELECT category_code,category_name,description FROM expense_categories WHERE category_id=%s FOR UPDATE',(category_id,))
        current=cursor.fetchone()
        if current is None:raise ExpenseCategoryError('Expense category no longer exists.',404)
        if tuple(current)==(category_code,category_name,description):
            connection.rollback();return False

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

        return True

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Expense category code already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise ExpenseCategoryError('Finance category data changed concurrently. Reload and try again.',409) from error
        raise

    finally:

        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


# ==========================================================
# ACTIVATE / DEACTIVATE EXPENSE CATEGORY
# ==========================================================

def set_expense_category_active_status(category_id, is_active):
    category_id=identifier(category_id,'Category')
    if type(is_active) is not bool:raise ExpenseCategoryError('Category status must be active or inactive.')
    connection=get_connection();cursor=None
    try:
        connection.start_transaction();cursor=connection.cursor();_require_category_storage(cursor)
        cursor.execute('SELECT is_active FROM expense_categories WHERE category_id=%s FOR UPDATE',(category_id,))
        current=cursor.fetchone()
        if current is None:raise ExpenseCategoryError('Expense category no longer exists.',404)
        if bool(current[0])==is_active:
            connection.rollback();return False
        # Serialize with the existing Finance reference FOR SHARE lock; leave
        # expense records, financial amounts and historical assignments untouched.
        cursor.execute('UPDATE expense_categories SET is_active=%s WHERE category_id=%s',(is_active,category_id))
        connection.commit();return True
    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None) in (1205,1213):raise ExpenseCategoryError('Finance category data changed concurrently. Reload and try again.',409) from error
        raise
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def _require_category_storage(cursor):
    # Finance tables are not covered by the global engine manifest. Fail closed
    # on unsupported category storage; never repair schemas or issue DDL here.
    cursor.execute("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='expense_categories'")
    row=cursor.fetchone()
    engine=row.get('ENGINE') if isinstance(row,dict) else row[0] if row else None
    if engine!='InnoDB':raise ExpenseCategoryError('Expense category storage is unavailable. Ask an administrator to verify the Finance schema.',503)


def get_expense_category_page(args):
    selected=category_filters(args)
    conditions,params=['1=1'],[]
    if selected['search']:
        literal='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        conditions.append("(category_code LIKE %s ESCAPE '!' OR category_name LIKE %s ESCAPE '!')")
        params.extend([literal]*2)
    if selected['status']:
        conditions.append('is_active=%s');params.append(selected['status']=='active')
    clause=' FROM expense_categories WHERE '+' AND '.join(conditions)
    connection=get_connection();cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True);_require_category_storage(cursor)
        cursor.execute('SELECT COUNT(*) AS total'+clause,tuple(params));total=cursor.fetchone()['total']
        pages=max(1,(total+selected['page_size']-1)//selected['page_size']);selected['page']=min(selected['page'],pages)
        cursor.execute('SELECT *'+clause+' ORDER BY category_name ASC,category_id ASC LIMIT %s OFFSET %s',
                       (*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        rows=cursor.fetchall();first=(selected['page']-1)*selected['page_size']+1 if total else 0
        return dict(records=rows,total=total,pages=pages,filters=selected,first=first,last=first+len(rows)-1 if rows else 0)
    finally:
        try:connection.rollback()
        finally:
            try:
                if cursor is not None:cursor.close()
            finally:connection.close()
