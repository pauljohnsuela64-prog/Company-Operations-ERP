from inventory_validation import category_fields
from database import get_connection
from inventory_category_management import CategoryError, identifier, filters as category_filters


def get_all_inventory_categories():
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
            FROM inventory_categories
            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_inventory_category_by_id(category_id):
    category_id = identifier(category_id)
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
                is_active
            FROM inventory_categories
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


def create_inventory_category(
    category_code,
    category_name,
    description=None,
):
    category_code, category_name, description = category_fields(category_code, category_name, description)
    connection = get_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO inventory_categories (
                category_code,
                category_name,
                description,
                is_active
            )
            VALUES (%s, %s, %s, TRUE)
            """,
            (
                category_code,
                category_name,
                description,
            ),
        )

        category_id = cursor.lastrowid
        connection.commit()
        return category_id

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Category code or category name already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise CategoryError('Inventory data changed concurrently. Reload and try again.',409) from error
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def update_inventory_category(
    category_id,
    category_code,
    category_name,
    description=None,
):
    category_id = identifier(category_id)
    category_code, category_name, description = category_fields(category_code, category_name, description)
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()
        connection.start_transaction()
        cursor.execute("SELECT category_code,category_name,description FROM inventory_categories WHERE category_id = %s FOR UPDATE", (category_id,))
        current=cursor.fetchone()
        if current is None:
            raise CategoryError('Inventory category no longer exists.',404)
        if tuple(current)==(category_code,category_name,description):
            connection.rollback()
            return False
        cursor.execute(
            """
            UPDATE inventory_categories
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
        if getattr(error,'errno',None)==1062:raise ValueError('Category code or category name already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise CategoryError('Inventory data changed concurrently. Reload and try again.',409) from error
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def set_inventory_category_active_status(category_id, is_active):
    category_id=identifier(category_id)
    if type(is_active) is not bool:raise CategoryError('Category status must be active or inactive.')
    connection=get_connection();cursor=None
    try:
        connection.start_transaction();cursor=connection.cursor()
        cursor.execute('SELECT is_active FROM inventory_categories WHERE category_id=%s FOR UPDATE',(category_id,))
        current=cursor.fetchone()
        if current is None:raise CategoryError('Inventory category no longer exists.',404)
        if bool(current[0])==is_active:
            connection.rollback();return False
        # Shares the category row boundary with item assignment FOR SHARE locks.
        # Existing item assignments and stock/history are never rewritten.
        cursor.execute('UPDATE inventory_categories SET is_active=%s WHERE category_id=%s',(is_active,category_id))
        connection.commit();return True
    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None) in (1205,1213):raise CategoryError('Inventory data changed concurrently. Reload and try again.',409) from error
        raise
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_active_inventory_categories():
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
            FROM inventory_categories
            WHERE is_active = TRUE
            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_inventory_category_page(args):
    selected=category_filters(args)
    conditions,params=['1=1'],[]
    if selected['search']:
        literal='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        conditions.append("(category_code LIKE %s ESCAPE '!' OR category_name LIKE %s ESCAPE '!')")
        params.extend([literal]*2)
    if selected['status']:
        conditions.append('is_active=%s');params.append(selected['status']=='active')
    clause=' FROM inventory_categories WHERE '+' AND '.join(conditions)
    connection=get_connection();cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
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
