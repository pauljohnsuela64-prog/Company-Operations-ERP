from inventory_validation import warehouse_fields
from database import get_connection
from warehouse_validation import WarehouseError, identifier, filters as warehouse_filters


def get_all_warehouses():
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                warehouse_id,
                warehouse_code,
                warehouse_name,
                location,
                is_active,
                created_at,
                updated_at
            FROM warehouses
            ORDER BY warehouse_name, warehouse_id
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_warehouse_by_id(warehouse_id):
    warehouse_id = identifier(warehouse_id)
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                warehouse_id,
                warehouse_code,
                warehouse_name,
                location,
                is_active
            FROM warehouses
            WHERE warehouse_id = %s
            LIMIT 1
            """,
            (warehouse_id,),
        )

        return cursor.fetchone()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def create_warehouse(
    warehouse_code,
    warehouse_name,
    location=None,
):
    warehouse_code, warehouse_name, location = warehouse_fields(warehouse_code, warehouse_name, location)
    connection = get_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO warehouses (
                warehouse_code,
                warehouse_name,
                location,
                is_active
            )
            VALUES (%s, %s, %s, TRUE)
            """,
            (
                warehouse_code,
                warehouse_name,
                location,
            ),
        )

        warehouse_id = cursor.lastrowid
        connection.commit()
        return warehouse_id

    except Exception:
        connection.rollback()
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def update_warehouse(warehouse_id, warehouse_code, warehouse_name, location=None):
    warehouse_id = identifier(warehouse_id)
    values = warehouse_fields(warehouse_code, warehouse_name, location)
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor()
        cursor.execute("SELECT warehouse_code,warehouse_name,location FROM warehouses WHERE warehouse_id=%s FOR UPDATE", (warehouse_id,))
        current = cursor.fetchone()
        if current is None:
            raise WarehouseError("Warehouse no longer exists.",404)
        if tuple(current) == values:
            connection.rollback()
            return False
        cursor.execute("UPDATE warehouses SET warehouse_code=%s,warehouse_name=%s,location=%s WHERE warehouse_id=%s", (*values,warehouse_id))
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def set_warehouse_active_status(warehouse_id, is_active):
    warehouse_id = identifier(warehouse_id)
    if type(is_active) is not bool:
        raise WarehouseError('Warehouse status must be active or inactive.')
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor()
        cursor.execute("SELECT is_active FROM warehouses WHERE warehouse_id=%s FOR UPDATE", (warehouse_id,))
        current = cursor.fetchone()
        if current is None:
            raise WarehouseError('Warehouse no longer exists.',404)
        if bool(current[0]) == is_active:
            connection.rollback()
            return False
        # The exclusive warehouse row lock serializes with stock/receipt eligibility
        # locks. Holding stock is deliberately NOT a deactivation restriction.
        cursor.execute("UPDATE warehouses SET is_active=%s WHERE warehouse_id=%s", (is_active,warehouse_id))
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_warehouse_page(args):
    selected=warehouse_filters(args)
    conditions,params=['1=1'],[]
    if selected['search']:
        literal='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        conditions.append("(warehouse_code LIKE %s ESCAPE '!' OR warehouse_name LIKE %s ESCAPE '!' OR location LIKE %s ESCAPE '!')")
        params.extend([literal]*3)
    if selected['status']:
        conditions.append('is_active=%s');params.append(selected['status']=='active')
    clause=' FROM warehouses WHERE '+' AND '.join(conditions)
    connection=get_connection();cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS total'+clause,tuple(params))
        total=cursor.fetchone()['total'];pages=max(1,(total+selected['page_size']-1)//selected['page_size'])
        selected['page']=min(selected['page'],pages)
        cursor.execute('SELECT warehouse_id,warehouse_code,warehouse_name,location,is_active,created_at,updated_at'+clause+
            ' ORDER BY warehouse_name,warehouse_id LIMIT %s OFFSET %s',(*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        rows=cursor.fetchall();first=(selected['page']-1)*selected['page_size']+1 if total else 0
        return dict(records=rows,total=total,pages=pages,filters=selected,first=first,last=first+len(rows)-1 if rows else 0)
    finally:
        try:connection.rollback()
        finally:
            try:
                if cursor is not None:cursor.close()
            finally:connection.close()
