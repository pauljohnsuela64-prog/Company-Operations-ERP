from inventory_validation import item_fields, lock_assignment_category
from database import get_connection
from inventory_item_management import ItemError, identifier, filters as item_filters


def get_all_inventory_items():
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                i.item_id,
                i.item_code,
                i.item_name,
                i.category_id,
                i.description,
                i.unit_of_measure,
                i.reorder_level,
                i.is_active,
                c.category_code,
                c.category_name
            FROM inventory_items i
            LEFT JOIN inventory_categories c
                ON i.category_id = c.category_id
            ORDER BY i.item_name
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_inventory_item_by_id(item_id):
    item_id = identifier(item_id)
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                item_id,
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
                is_active
            FROM inventory_items
            WHERE item_id = %s
            LIMIT 1
            """,
            (item_id,),
        )

        return cursor.fetchone()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def create_inventory_item(
    item_code,
    item_name,
    category_id,
    description,
    unit_of_measure,
    reorder_level,
):
    item_code, item_name, category_id, description, unit_of_measure, reorder_level = item_fields(
        item_code, item_name, category_id, description, unit_of_measure, reorder_level)
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()
        connection.start_transaction()
        lock_assignment_category(cursor, category_id)
        cursor.execute(
            """
            INSERT INTO inventory_items (
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
            ),
        )

        item_id = cursor.lastrowid
        connection.commit()
        return item_id

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Item code already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise ItemError('Inventory data changed concurrently. Reload and try again.',409) from error
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def update_inventory_item(
    item_id,
    item_code,
    item_name,
    category_id,
    description,
    unit_of_measure,
    reorder_level,
):
    item_id = identifier(item_id)
    item_code, item_name, category_id, description, unit_of_measure, reorder_level = item_fields(
        item_code, item_name, category_id, description, unit_of_measure, reorder_level)
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()
        connection.start_transaction()
        cursor.execute("SELECT category_id,item_code,item_name,description,unit_of_measure,reorder_level FROM inventory_items WHERE item_id = %s FOR UPDATE", (item_id,))
        existing = cursor.fetchone()
        if not existing:
            raise ItemError("Inventory item no longer exists.",404)
        lock_assignment_category(cursor, category_id, existing[0])
        if tuple(existing) == (category_id,item_code,item_name,description,unit_of_measure,reorder_level):
            connection.rollback()
            return False
        cursor.execute(
            """
            UPDATE inventory_items
            SET
                item_code = %s,
                item_name = %s,
                category_id = %s,
                description = %s,
                unit_of_measure = %s,
                reorder_level = %s
            WHERE item_id = %s
            """,
            (
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
                item_id,
            ),
        )

        connection.commit()
        return True

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Item code already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise ItemError('Inventory data changed concurrently. Reload and try again.',409) from error
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def set_inventory_item_active_status(item_id, is_active):
    item_id=identifier(item_id)
    if type(is_active) is not bool:raise ItemError('Item status must be active or inactive.')
    connection=get_connection();cursor=None
    try:
        connection.start_transaction();cursor=connection.cursor()
        cursor.execute('SELECT is_active FROM inventory_items WHERE item_id=%s FOR UPDATE',(item_id,))
        current=cursor.fetchone()
        if current is None:raise ItemError('Inventory item no longer exists.',404)
        if bool(current[0])==is_active:
            connection.rollback();return False
        # Serializes with manual stock/Procurement item eligibility locks. Stock holdings do
        # not prevent deactivation; historical stock and movements stay untouched.
        cursor.execute('UPDATE inventory_items SET is_active=%s WHERE item_id=%s',(is_active,item_id))
        connection.commit();return True
    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None) in (1205,1213):raise ItemError('Inventory data changed concurrently. Reload and try again.',409) from error
        raise
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_active_inventory_items():
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                item_id,
                item_code,
                item_name,
                unit_of_measure
            FROM inventory_items
            WHERE is_active = TRUE
            ORDER BY item_name
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_inventory_item_page(args):
    selected=item_filters(args)
    conditions,params=['1=1'],[]
    if selected['search']:
        literal='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        conditions.append("(i.item_code LIKE %s ESCAPE '!' OR i.item_name LIKE %s ESCAPE '!')")
        params.extend([literal]*2)
    if selected['category_id']=='none':conditions.append('i.category_id IS NULL')
    elif selected['category_id']!='':
        conditions.append('i.category_id=%s');params.append(selected['category_id'])
    if selected['status']:
        conditions.append('i.is_active=%s');params.append(selected['status']=='active')
    clause=' FROM inventory_items i LEFT JOIN inventory_categories c ON i.category_id=c.category_id WHERE '+' AND '.join(conditions)
    connection=get_connection();cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS total'+clause,tuple(params));total=cursor.fetchone()['total']
        pages=max(1,(total+selected['page_size']-1)//selected['page_size']);selected['page']=min(selected['page'],pages)
        cursor.execute('SELECT i.*,c.category_code,c.category_name'+clause+' ORDER BY i.item_name ASC,i.item_id ASC LIMIT %s OFFSET %s',
                       (*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        rows=cursor.fetchall();first=(selected['page']-1)*selected['page_size']+1 if total else 0
        return dict(records=rows,total=total,pages=pages,filters=selected,first=first,last=first+len(rows)-1 if rows else 0)
    finally:
        try:connection.rollback()
        finally:
            try:
                if cursor is not None:cursor.close()
            finally:connection.close()
