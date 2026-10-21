from supplier_management import SupplierError, identifier, fields, filters as supplier_filters
from database import get_connection


def get_all_suppliers():
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                supplier_id,
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                is_active,
                created_at,
                updated_at
            FROM suppliers
            ORDER BY supplier_name
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_supplier_by_id(supplier_id):
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                supplier_id,
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                is_active
            FROM suppliers
            WHERE supplier_id = %s
            LIMIT 1
            """,
            (supplier_id,),
        )

        return cursor.fetchone()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def create_supplier(
    supplier_code,
    supplier_name,
    contact_person=None,
    email=None,
    phone=None,
    address=None,
):
    supplier_code, supplier_name, contact_person, email, phone, address = fields(
        supplier_code, supplier_name, contact_person, email, phone, address)
    connection = get_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO suppliers (
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
            ),
        )

        supplier_id = cursor.lastrowid
        connection.commit()
        return supplier_id

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Supplier code already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise SupplierError('Supplier data changed concurrently. Reload and try again.',409) from error
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def update_supplier(
    supplier_id,
    supplier_code,
    supplier_name,
    contact_person=None,
    email=None,
    phone=None,
    address=None,
):
    supplier_id=identifier(supplier_id)
    supplier_code, supplier_name, contact_person, email, phone, address = fields(
        supplier_code, supplier_name, contact_person, email, phone, address)
    connection = get_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        cursor.execute('SELECT supplier_code,supplier_name,contact_person,email,phone,address FROM suppliers WHERE supplier_id=%s FOR UPDATE',(supplier_id,))
        current=cursor.fetchone()
        if current is None:raise SupplierError('Supplier no longer exists.',404)
        if tuple(current)==(supplier_code,supplier_name,contact_person,email,phone,address):
            connection.rollback();return False
        cursor.execute(
            """
            UPDATE suppliers
            SET
                supplier_code = %s,
                supplier_name = %s,
                contact_person = %s,
                email = %s,
                phone = %s,
                address = %s
            WHERE supplier_id = %s
            """,
            (
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                supplier_id,
            ),
        )

        connection.commit()
        return True

    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None)==1062:raise ValueError('Supplier code already exists.') from error
        if getattr(error,'errno',None) in (1205,1213):raise SupplierError('Supplier data changed concurrently. Reload and try again.',409) from error
        raise

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def set_supplier_active_status(supplier_id, is_active):
    supplier_id=identifier(supplier_id)
    if type(is_active) is not bool:raise SupplierError('Supplier status must be active or inactive.')
    connection=get_connection();cursor=None
    try:
        connection.start_transaction();cursor=connection.cursor()
        cursor.execute('SELECT is_active FROM suppliers WHERE supplier_id=%s FOR UPDATE',(supplier_id,))
        current=cursor.fetchone()
        if current is None:raise SupplierError('Supplier no longer exists.',404)
        if bool(current[0])==is_active:
            connection.rollback();return False
        # Serialize with Finance supplier reference locks. Do not rewrite PO,
        # expense, stock or historical records, or change their eligibility rules.
        cursor.execute('UPDATE suppliers SET is_active=%s WHERE supplier_id=%s',(is_active,supplier_id))
        connection.commit();return True
    except Exception as error:
        connection.rollback()
        if getattr(error,'errno',None) in (1205,1213):raise SupplierError('Supplier data changed concurrently. Reload and try again.',409) from error
        raise
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_active_suppliers():
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                supplier_id,
                supplier_code,
                supplier_name
            FROM suppliers
            WHERE is_active = TRUE
            ORDER BY supplier_name
            """
        )

        return cursor.fetchall()

    finally:
        try:
            if cursor is not None:cursor.close()
        finally:connection.close()


def get_supplier_page(args):
    selected=supplier_filters(args)
    conditions,params=['1=1'],[]
    if selected['search']:
        literal='%'+selected['search'].replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        conditions.append("(supplier_code LIKE %s ESCAPE '!' OR supplier_name LIKE %s ESCAPE '!')")
        params.extend([literal]*2)
    if selected['status']:
        conditions.append('is_active=%s');params.append(selected['status']=='active')
    clause=' FROM suppliers WHERE '+' AND '.join(conditions)
    connection=get_connection();cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS total'+clause,tuple(params));total=cursor.fetchone()['total']
        pages=max(1,(total+selected['page_size']-1)//selected['page_size']);selected['page']=min(selected['page'],pages)
        cursor.execute('SELECT *'+clause+' ORDER BY supplier_name ASC,supplier_id ASC LIMIT %s OFFSET %s',
                       (*params,selected['page_size'],(selected['page']-1)*selected['page_size']))
        rows=cursor.fetchall();first=(selected['page']-1)*selected['page_size']+1 if total else 0
        return dict(records=rows,total=total,pages=pages,filters=selected,first=first,last=first+len(rows)-1 if rows else 0)
    finally:
        try:connection.rollback()
        finally:
            try:
                if cursor is not None:cursor.close()
            finally:connection.close()
