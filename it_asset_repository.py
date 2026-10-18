from it_asset_validation import (asset_values, identifier, calendar_date, cost as validate_cost, text,
                                 category_values, lock_references, lock_employee, translate_write_error)
# ==========================================================
# IT MANAGEMENT - IT ASSET REPOSITORY
# ==========================================================

from database import get_connection


# ==========================================================
# GET ALL ASSET CATEGORIES
# ==========================================================

def get_all_it_asset_categories():
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

            FROM it_asset_categories

            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ACTIVE ASSET CATEGORIES
# ==========================================================

def get_active_it_asset_categories():
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
                is_active

            FROM it_asset_categories

            WHERE is_active = TRUE

            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ALL IT ASSETS
# ==========================================================

def get_all_it_assets():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                a.asset_id,
                a.asset_tag,
                a.asset_name,

                a.category_id,
                c.category_code,
                c.category_name,

                a.brand,
                a.model,
                a.serial_number,

                a.department_id,
                d.department_name,

                a.assigned_employee_id,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS assigned_employee_name,

                a.purchase_date,
                a.purchase_cost,
                a.warranty_expiry,

                a.status,
                a.condition_status,
                a.notes,

                a.created_by,
                u.username AS created_by_username,

                a.created_at,
                a.updated_at

            FROM it_assets a

            INNER JOIN it_asset_categories c
                ON a.category_id = c.category_id

            LEFT JOIN departments d
                ON a.department_id = d.department_id

            LEFT JOIN employees e
                ON a.assigned_employee_id = e.employee_id

            INNER JOIN users u
                ON a.created_by = u.user_id

            ORDER BY
                a.asset_name,
                a.asset_tag
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET IT ASSET BY ID
# ==========================================================

def get_it_asset_by_id(asset_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                a.*,

                c.category_code,
                c.category_name,

                d.department_name,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS assigned_employee_name,

                u.username AS created_by_username

            FROM it_assets a

            INNER JOIN it_asset_categories c
                ON a.category_id = c.category_id

            LEFT JOIN departments d
                ON a.department_id = d.department_id

            LEFT JOIN employees e
                ON a.assigned_employee_id = e.employee_id

            INNER JOIN users u
                ON a.created_by = u.user_id

            WHERE a.asset_id = %s

            LIMIT 1
            """,
            (asset_id,),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE IT ASSET
# ==========================================================

def create_it_asset(
    asset_tag,
    asset_name,
    category_id,
    brand,
    model,
    serial_number,
    department_id,
    assigned_employee_id,
    purchase_date,
    purchase_cost,
    warranty_expiry,
    status,
    condition_status,
    notes,
    created_by,
):
    (asset_tag, asset_name, category_id, brand, model, serial_number,
     department_id, purchase_date, purchase_cost, warranty_expiry,
     condition_status, notes) = asset_values(locals())
    assigned_employee_id = identifier(assigned_employee_id, 'Employee', True)
    created_by = identifier(created_by, 'Creator')
    if status not in ('AVAILABLE','ASSIGNED','MAINTENANCE','LOST','RETIRED'):
        raise ValueError('Invalid asset status.')
    if (status == 'ASSIGNED' and assigned_employee_id is None) or (status == 'AVAILABLE' and assigned_employee_id is not None):
        raise ValueError('Asset status does not match its assignment.')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()
        lock_references(cursor, category_id, department_id, assigned_employee_id)

        cursor.execute(
            """
            INSERT INTO it_assets (
                asset_tag,
                asset_name,
                category_id,
                brand,
                model,
                serial_number,
                department_id,
                assigned_employee_id,
                purchase_date,
                purchase_cost,
                warranty_expiry,
                status,
                condition_status,
                notes,
                created_by
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                asset_tag,
                asset_name,
                category_id,
                brand,
                model,
                serial_number,
                department_id,
                assigned_employee_id,
                purchase_date,
                purchase_cost,
                warranty_expiry,
                status,
                condition_status,
                notes,
                created_by,
            ),
        )

        asset_id = cursor.lastrowid
        if assigned_employee_id is not None:
            cursor.execute(
                """INSERT INTO it_asset_assignments
                   (asset_id, employee_id, department_id, assigned_by)
                   VALUES (%s, %s, %s, %s)""",
                (asset_id, assigned_employee_id, department_id, created_by),
            )
        connection.commit()
        return asset_id

    except Exception as error:
        connection.rollback()
        translated = translate_write_error(error)
        if translated is error:
            raise
        raise translated from error

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# UPDATE IT ASSET
# ==========================================================

def update_it_asset(
    asset_id,
    asset_tag,
    asset_name,
    category_id,
    brand,
    model,
    serial_number,
    department_id,
    purchase_date,
    purchase_cost,
    warranty_expiry,
    condition_status,
    notes,
):
    (asset_tag, asset_name, category_id, brand, model, serial_number,
     department_id, purchase_date, purchase_cost, warranty_expiry,
     condition_status, notes) = asset_values(locals())
    asset_id = identifier(asset_id, 'Asset')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT asset_id, category_id, department_id
            FROM it_assets
            WHERE asset_id = %s
            FOR UPDATE
            """,
            (asset_id,),
        )

        previous = cursor.fetchone()
        if not previous:
            raise ValueError(
                "IT asset was not found."
            )

        lock_references(cursor, category_id, department_id, previous=previous)

        cursor.execute(
            """
            UPDATE it_assets
            SET
                asset_tag = %s,
                asset_name = %s,
                category_id = %s,
                brand = %s,
                model = %s,
                serial_number = %s,
                department_id = %s,
                purchase_date = %s,
                purchase_cost = %s,
                warranty_expiry = %s,
                condition_status = %s,
                notes = %s

            WHERE asset_id = %s
            """,
            (
                asset_tag,
                asset_name,
                category_id,
                brand,
                model,
                serial_number,
                department_id,
                purchase_date,
                purchase_cost,
                warranty_expiry,
                condition_status,
                notes,
                asset_id,
            ),
        )

        connection.commit()
        return cursor.rowcount == 1

    except Exception as error:
        connection.rollback()
        translated = translate_write_error(error)
        if translated is error:
            raise
        raise translated from error

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# ASSIGN IT ASSET
# ==========================================================

def assign_it_asset(
    asset_id,
    employee_id,
    department_id,
    assigned_by,
):
    asset_id = identifier(asset_id, 'Asset')
    employee_id = identifier(employee_id, 'Employee')
    department_id = identifier(department_id, 'Department', True)
    assigned_by = identifier(assigned_by, 'Assigning user')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()


        # ==================================================
        # LOCK ASSET
        # ==========================================================

        cursor.execute(
            """
            SELECT
                asset_id,
                status,
                assigned_employee_id

            FROM it_assets

            WHERE asset_id = %s

            FOR UPDATE
            """,
            (asset_id,),
        )

        asset = cursor.fetchone()

        if not asset:

            raise ValueError(
                "IT asset was not found."
            )


        # ==================================================
        # BUSINESS RULES
        # ==========================================================

        if asset["status"] in (
            "MAINTENANCE",
            "RETIRED",
            "LOST",
        ):

            raise ValueError(
                "Assets under maintenance, retired, "
                "or lost cannot be assigned."
            )

        if asset["assigned_employee_id"] is not None:

            raise ValueError(
                "This asset is already assigned."
            )


        lock_employee(cursor, employee_id)
        if department_id is not None:
            cursor.execute('SELECT department_id FROM departments WHERE department_id=%s FOR SHARE', (department_id,))
            if not cursor.fetchone():
                raise ValueError('Selected department does not exist.')

        if asset['status'] != 'AVAILABLE':
            raise ValueError('Only available assets can be assigned.')
        cursor.execute(
            """SELECT assignment_id FROM it_asset_assignments
               WHERE asset_id = %s AND returned_at IS NULL FOR UPDATE""",
            (asset_id,),
        )
        if cursor.fetchall():
            raise ValueError('Assignment history is inconsistent. Review it before assigning this asset.')

        # ==================================================
        # UPDATE CURRENT ASSET
        # ==========================================================

        cursor.execute(
            """
            UPDATE it_assets

            SET
                assigned_employee_id = %s,
                department_id = %s,
                status = 'ASSIGNED'

            WHERE asset_id = %s
            """,
            (
                employee_id,
                department_id,
                asset_id,
            ),
        )


        # ==================================================
        # CREATE ASSIGNMENT HISTORY
        # ==========================================================

        cursor.execute(
            """
            INSERT INTO it_asset_assignments (
                asset_id,
                employee_id,
                department_id,
                assigned_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                asset_id,
                employee_id,
                department_id,
                assigned_by,
            ),
        )


        connection.commit()
        return True

    except Exception as error:
        connection.rollback()
        translated = translate_write_error(error)
        if translated is error:
            raise
        raise translated from error

    finally:

        cursor.close()
        connection.close()
        

# ==========================================================
# UNASSIGN IT ASSET
# ==========================================================

def unassign_it_asset(asset_id, returned_by, assignment_id=None):
    """Close the displayed custody record without erasing lifecycle state.

    All lifecycle writers lock asset first, then their child history records.
    A required expected assignment ID rejects stale forms, including reassignments
    to the same employee. Never invent missing historical custody records.
    """
    expected = str(assignment_id).strip()
    if (len(expected) > 10 or not expected.isascii() or not expected.isdecimal()
            or not 1 <= int(expected) <= 2147483647):
        raise ValueError('Current assignment is required. Reload the asset and try again.')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        cursor.execute(
            'SELECT asset_id, assigned_employee_id, status FROM it_assets WHERE asset_id = %s FOR UPDATE',
            (asset_id,),
        )
        asset = cursor.fetchone()
        if not asset:
            raise ValueError('IT asset was not found.')
        if asset['assigned_employee_id'] is None:
            raise ValueError('This asset is not currently assigned.')
        if asset['status'] == 'LOST':
            raise ValueError('Recover this asset before returning it.')
        if asset['status'] == 'MAINTENANCE':
            raise ValueError('Complete maintenance before returning this asset.')
        if asset['status'] not in ('ASSIGNED', 'RETIRED'):
            raise ValueError('Asset state is inconsistent with its assignment. Review it before returning.')
        cursor.execute(
            """SELECT assignment_id, employee_id FROM it_asset_assignments
               WHERE asset_id = %s AND returned_at IS NULL
               ORDER BY assignment_id FOR UPDATE""",
            (asset_id,),
        )
        active = cursor.fetchall()
        if len(active) != 1 or active[0]['employee_id'] != asset['assigned_employee_id']:
            raise ValueError('Assignment history is missing or inconsistent. Review it before returning this asset.')
        if active[0]['assignment_id'] != int(expected):
            raise ValueError('Assignment changed. Reload the asset before returning it.')
        cursor.execute(
            "SELECT maintenance_id FROM it_asset_maintenance WHERE asset_id = %s AND status = 'OPEN' FOR UPDATE",
            (asset_id,),
        )
        open_maintenance = cursor.fetchall()
        if asset['status'] == 'ASSIGNED' and open_maintenance:
            raise ValueError('Asset state does not match open maintenance. Review it before returning.')
        cursor.execute(
            """UPDATE it_asset_assignments SET returned_at = CURRENT_TIMESTAMP, returned_by = %s
               WHERE assignment_id = %s AND returned_at IS NULL""",
            (returned_by, int(expected)),
        )
        if cursor.rowcount != 1:
            raise ValueError('Assignment changed. Reload the asset before returning it.')
        # Returning custody is not recovery, maintenance completion or restoration.
        status = 'AVAILABLE' if asset['status'] == 'ASSIGNED' else asset['status']
        cursor.execute('UPDATE it_assets SET assigned_employee_id = NULL, status = %s WHERE asset_id = %s',
                       (status, asset_id))
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


# ==========================================================
# GET ASSET MAINTENANCE HISTORY
# ==========================================================


def get_it_asset_maintenance_history(asset_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                m.maintenance_id,
                m.asset_id,
                m.maintenance_type,
                m.description,
                m.vendor,
                m.cost,
                m.start_date,
                m.completed_date,
                m.status,
                m.notes,
                m.created_by,

                u.username AS created_by_username,

                m.created_at,
                m.updated_at

            FROM it_asset_maintenance m

            INNER JOIN users u
                ON m.created_by = u.user_id

            WHERE m.asset_id = %s

            ORDER BY
                m.start_date DESC,
                m.maintenance_id DESC
            """,
            (asset_id,),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE MAINTENANCE RECORD
#
# Automatically places asset into MAINTENANCE status.
# ==========================================================

def create_it_asset_maintenance(
    asset_id,
    maintenance_type,
    description,
    vendor,
    cost,
    start_date,
    notes,
    created_by,
):
    asset_id = identifier(asset_id, 'Asset')
    created_by = identifier(created_by, 'Creator')
    maintenance_type = text(maintenance_type, 'Maintenance type', 50, True)
    description = text(description, 'Description', 255, True)
    vendor = text(vendor, 'Vendor', 150)
    notes = text(notes, 'Notes', 255)
    cost = validate_cost(cost, 'Maintenance cost')
    start_date = calendar_date(start_date, 'Start date')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()


        # ==================================================
        # LOCK ASSET
        # ==========================================================

        cursor.execute(
            """
            SELECT
                asset_id,
                status

            FROM it_assets

            WHERE asset_id = %s

            FOR UPDATE
            """,
            (asset_id,),
        )

        asset = cursor.fetchone()

        if not asset:
            raise ValueError(
                "IT asset was not found."
            )

        if asset["status"] in (
            "RETIRED",
            "LOST",
        ):
            raise ValueError(
                "Retired or lost assets cannot be placed "
                "into maintenance."
            )


        # ==================================================
        # PREVENT MULTIPLE OPEN MAINTENANCE RECORDS
        # ==========================================================

        cursor.execute(
            """
            SELECT maintenance_id

            FROM it_asset_maintenance

            WHERE
                asset_id = %s
                AND status = 'OPEN'

            LIMIT 1

            FOR UPDATE
            """,
            (asset_id,),
        )

        if cursor.fetchone():

            raise ValueError(
                "This asset already has an open "
                "maintenance record."
            )


        # ==================================================
        # CREATE MAINTENANCE
        # ==========================================================

        cursor.execute(
            """
            INSERT INTO it_asset_maintenance (
                asset_id,
                maintenance_type,
                description,
                vendor,
                cost,
                start_date,
                status,
                notes,
                created_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'OPEN',
                %s,
                %s
            )
            """,
            (
                asset_id,
                maintenance_type,
                description,
                vendor,
                cost,
                start_date,
                notes,
                created_by,
            ),
        )

        maintenance_id = cursor.lastrowid


        # ==================================================
        # UPDATE ASSET STATUS
        # ==========================================================

        cursor.execute(
            """
            UPDATE it_assets

            SET status = 'MAINTENANCE'

            WHERE asset_id = %s
            """,
            (asset_id,),
        )

        connection.commit()

        return maintenance_id

    except Exception as error:
        connection.rollback()
        translated = translate_write_error(error)
        if translated is error:
            raise
        raise translated from error

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# COMPLETE MAINTENANCE
#
# Restores asset to:
# - ASSIGNED if it still has an employee
# - AVAILABLE if unassigned
# ==========================================================

def complete_it_asset_maintenance(
    maintenance_id,
    completed_date,
):
    maintenance_id = identifier(maintenance_id, 'Maintenance')
    completed_date = calendar_date(completed_date, 'Completion date')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()


        # Resolve the parent without locking the child, then lock parent first.
        cursor.execute('SELECT asset_id FROM it_asset_maintenance WHERE maintenance_id = %s',
                       (maintenance_id,))
        parent = cursor.fetchone()
        if not parent:
            raise ValueError('Maintenance record was not found.')
        cursor.execute('SELECT asset_id, status FROM it_assets WHERE asset_id = %s FOR UPDATE',
                       (parent['asset_id'],))
        asset = cursor.fetchone()
        if not asset:
            raise ValueError('IT asset was not found.')

        # ==================================================
        # LOCK MAINTENANCE RECORD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                maintenance_id,
                asset_id,
                status,
                start_date

            FROM it_asset_maintenance

            WHERE maintenance_id = %s

            FOR UPDATE
            """,
            (maintenance_id,),
        )

        maintenance = cursor.fetchone()

        if not maintenance:

            raise ValueError(
                "Maintenance record was not found."
            )

        if maintenance['asset_id'] != asset['asset_id']:
            raise ValueError('Maintenance changed concurrently. Reload and try again.')
        if maintenance["status"] != "OPEN":

            raise ValueError(
                "Only open maintenance records "
                "can be completed."
            )


        start_date = calendar_date(maintenance['start_date'], 'Maintenance start date')
        if completed_date < start_date:
            raise ValueError('Completion date cannot be before maintenance start date.')

        if asset['status'] != 'MAINTENANCE':
            raise ValueError('Asset state does not match open maintenance. Review it before completion.')

        cursor.execute(
            "SELECT maintenance_id FROM it_asset_maintenance WHERE asset_id = %s AND status = 'OPEN' FOR UPDATE",
            (asset['asset_id'],),
        )
        active = cursor.fetchall()
        if len(active) != 1 or str(active[0]['maintenance_id']) != str(maintenance_id):
            raise ValueError('Maintenance history is inconsistent. Review it before completion.')

        # ==================================================
        # COMPLETE MAINTENANCE
        # ==========================================================

        cursor.execute(
            """
            UPDATE it_asset_maintenance

            SET
                status = 'COMPLETED',
                completed_date = %s

            WHERE maintenance_id = %s
            """,
            (
                completed_date,
                maintenance_id,
            ),
        )


        # ==================================================
        # RESTORE ASSET STATUS
        # ==========================================================

        cursor.execute(
            """
            UPDATE it_assets

            SET status =
                CASE
                    WHEN assigned_employee_id IS NULL
                        THEN 'AVAILABLE'
                    ELSE 'ASSIGNED'
                END

            WHERE asset_id = %s
            """,
            (
                maintenance["asset_id"],
            ),
        )

        connection.commit()

        return maintenance["asset_id"]

    except Exception as error:
        connection.rollback()
        translated = translate_write_error(error)
        if translated is error:
            raise
        raise translated from error

    finally:

        cursor.close()
        connection.close()

# ==========================================================
# GET IT ASSET SUMMARY
# ==========================================================

def get_it_asset_summary(connection=None):
    owns_connection = connection is None
    connection = connection if connection is not None else get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_assets,

                COALESCE(
                    SUM(status = 'AVAILABLE'),
                    0
                ) AS available_count,

                COALESCE(
                    SUM(status = 'ASSIGNED'),
                    0
                ) AS assigned_count,

                COALESCE(
                    SUM(status = 'MAINTENANCE'),
                    0
                ) AS maintenance_count,

                COALESCE(
                    SUM(status = 'RETIRED'),
                    0
                ) AS retired_count,

                COALESCE(
                    SUM(status = 'LOST'),
                    0
                ) AS lost_count

            FROM it_assets
            """
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        if owns_connection:
            connection.close()


# ==========================================================
# GET FILTERED IT ASSETS
# ==========================================================

def get_filtered_it_assets(
    search_text=None,
    status=None,
    category_id=None,
    department_id=None,
    connection=None,
):
    owns_connection = connection is None
    connection = connection if connection is not None else get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        query = """
            SELECT
                a.asset_id,
                a.asset_tag,
                a.asset_name,

                a.category_id,
                c.category_code,
                c.category_name,

                a.brand,
                a.model,
                a.serial_number,

                a.department_id,
                d.department_name,

                a.assigned_employee_id,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS assigned_employee_name,

                a.purchase_date,
                a.purchase_cost,
                a.warranty_expiry,

                a.status,
                a.condition_status,
                a.notes,

                a.created_at,
                a.updated_at

            FROM it_assets a

            INNER JOIN it_asset_categories c
                ON a.category_id = c.category_id

            LEFT JOIN departments d
                ON a.department_id = d.department_id

            LEFT JOIN employees e
                ON a.assigned_employee_id = e.employee_id

            WHERE 1 = 1
        """

        parameters = []


        # ==================================================
        # SEARCH
        # ==========================================================

        if search_text:

            search_value = f"%{search_text}%"

            query += """
                AND (
                    a.asset_tag LIKE %s
                    OR a.asset_name LIKE %s
                    OR a.brand LIKE %s
                    OR a.model LIKE %s
                    OR a.serial_number LIKE %s
                    OR d.department_name LIKE %s
                    OR CONCAT(
                        e.first_name,
                        ' ',
                        e.last_name
                    ) LIKE %s
                )
            """

            parameters.extend(
                [
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                ]
            )


        # ==================================================
        # STATUS
        # ==========================================================

        if status:

            query += """
                AND a.status = %s
            """

            parameters.append(status)


        # ==================================================
        # CATEGORY
        # ==========================================================

        if category_id is not None:

            query += """
                AND a.category_id = %s
            """

            parameters.append(category_id)


        # ==================================================
        # DEPARTMENT
        # ==========================================================

        if department_id is not None:

            query += """
                AND a.department_id = %s
            """

            parameters.append(department_id)


        query += """
            ORDER BY
                a.asset_name,
                a.asset_tag
        """

        cursor.execute(
            query,
            tuple(parameters),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        if owns_connection:
            connection.close()


# ==========================================================
# MARK IT ASSET AS RETIRED
# ==========================================================

def retire_it_asset(asset_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                asset_id,
                status,
                assigned_employee_id

            FROM it_assets

            WHERE asset_id = %s

            FOR UPDATE
            """,
            (asset_id,),
        )

        asset = cursor.fetchone()

        if not asset:
            raise ValueError(
                "IT asset was not found."
            )

        if asset["status"] == "RETIRED":
            raise ValueError(
                "This asset is already retired."
            )

        if asset["status"] == "LOST":
            raise ValueError(
                "A lost asset must be recovered before it can be retired."
            )

        if asset["status"] == "MAINTENANCE":
            raise ValueError(
                "Complete the open maintenance record before retiring this asset."
            )

        if asset["assigned_employee_id"] is not None:
            raise ValueError(
                "Unassign the asset before retiring it."
            )

        cursor.execute(
            """
            UPDATE it_assets
            SET status = 'RETIRED'
            WHERE asset_id = %s
            """,
            (asset_id,),
        )

        connection.commit()
        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# MARK IT ASSET AS LOST
# ==========================================================

def mark_it_asset_lost(asset_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                asset_id,
                status

            FROM it_assets

            WHERE asset_id = %s

            FOR UPDATE
            """,
            (asset_id,),
        )

        asset = cursor.fetchone()

        if not asset:
            raise ValueError(
                "IT asset was not found."
            )

        if asset["status"] == "LOST":
            raise ValueError(
                "This asset is already marked as lost."
            )

        if asset["status"] == "RETIRED":
            raise ValueError(
                "A retired asset cannot be marked as lost."
            )

        if asset["status"] == "MAINTENANCE":
            raise ValueError(
                "Complete the open maintenance record before marking this asset as lost."
            )

        cursor.execute(
            """
            UPDATE it_assets
            SET status = 'LOST'
            WHERE asset_id = %s
            """,
            (asset_id,),
        )

        connection.commit()
        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# RESTORE LOST / RETIRED ASSET
# ==========================================================

def restore_it_asset(asset_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                asset_id,
                status,
                assigned_employee_id

            FROM it_assets

            WHERE asset_id = %s

            FOR UPDATE
            """,
            (asset_id,),
        )

        asset = cursor.fetchone()

        if not asset:
            raise ValueError(
                "IT asset was not found."
            )

        if asset["status"] not in (
            "LOST",
            "RETIRED",
        ):
            raise ValueError(
                "Only lost or retired assets can be restored."
            )

        restored_status = (
            "ASSIGNED"
            if asset["assigned_employee_id"] is not None
            else "AVAILABLE"
        )

        cursor.execute(
            """
            UPDATE it_assets
            SET status = %s
            WHERE asset_id = %s
            """,
            (
                restored_status,
                asset_id,
            ),
        )

        connection.commit()
        return asset['status']

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET IT ASSET ASSIGNMENT HISTORY
# ==========================================================

def get_it_asset_assignment_history(
    asset_id,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                a.assignment_id,
                a.asset_id,
                a.employee_id,
                a.department_id,

                e.employee_number,

                CONCAT(
                    e.first_name,
                    ' ',
                    e.last_name
                ) AS employee_name,

                d.department_name,

                a.assigned_at,
                a.returned_at,

                assigned_user.username
                    AS assigned_by_username,

                returned_user.username
                    AS returned_by_username,

                a.notes

            FROM it_asset_assignments a

            INNER JOIN employees e
                ON a.employee_id = e.employee_id

            LEFT JOIN departments d
                ON a.department_id = d.department_id

            INNER JOIN users assigned_user
                ON a.assigned_by
                = assigned_user.user_id

            LEFT JOIN users returned_user
                ON a.returned_by
                = returned_user.user_id

            WHERE a.asset_id = %s

            ORDER BY
                a.assigned_at DESC,
                a.assignment_id DESC
            """,
            (asset_id,),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()

# ==========================================================
# GET IT ASSET CATEGORY BY ID
# ==========================================================

def get_it_asset_category_by_id(category_id):
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

            FROM it_asset_categories

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
# CREATE IT ASSET CATEGORY
# ==========================================================

def create_it_asset_category(
    category_code,
    category_name,
    description,
):
    category_code, category_name, description = category_values(category_code, category_name, description)
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO it_asset_categories (
                category_code,
                category_name,
                description
            )
            VALUES (
                %s,
                %s,
                %s
            )
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
# UPDATE IT ASSET CATEGORY
# ==========================================================

def update_it_asset_category(
    category_id,
    category_code,
    category_name,
    description,
):
    category_code, category_name, description = category_values(category_code, category_name, description)
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE it_asset_categories

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
# CHANGE IT ASSET CATEGORY STATUS
# ==========================================================

def set_it_asset_category_active_status(
    category_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE it_asset_categories

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


# ==========================================================
# IT ASSET REPORT - BY CATEGORY
# ==========================================================

def get_it_asset_report_by_category(connection=None):
    owns_connection = connection is None
    connection = connection if connection is not None else get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                c.category_id,
                c.category_code,
                c.category_name,

                COUNT(a.asset_id) AS total_assets,

                COALESCE(
                    SUM(a.status = 'AVAILABLE'),
                    0
                ) AS available_count,

                COALESCE(
                    SUM(a.status = 'ASSIGNED'),
                    0
                ) AS assigned_count,

                COALESCE(
                    SUM(a.status = 'MAINTENANCE'),
                    0
                ) AS maintenance_count,

                COALESCE(
                    SUM(a.status = 'RETIRED'),
                    0
                ) AS retired_count,

                COALESCE(
                    SUM(a.status = 'LOST'),
                    0
                ) AS lost_count,

                COALESCE(
                    SUM(a.purchase_cost),
                    0
                ) AS total_purchase_cost

            FROM it_asset_categories c

            LEFT JOIN it_assets a
                ON c.category_id = a.category_id

            GROUP BY
                c.category_id,
                c.category_code,
                c.category_name

            ORDER BY
                c.category_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        if owns_connection:
            connection.close()


# ==========================================================
# IT ASSET REPORT - BY DEPARTMENT
# ==========================================================

def get_it_asset_report_by_department(connection=None):
    owns_connection = connection is None
    connection = connection if connection is not None else get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                a.department_id,

                COALESCE(
                    d.department_name,
                    'No Department'
                ) AS department_name,

                COUNT(a.asset_id) AS total_assets,

                COALESCE(
                    SUM(a.status = 'AVAILABLE'),
                    0
                ) AS available_count,

                COALESCE(
                    SUM(a.status = 'ASSIGNED'),
                    0
                ) AS assigned_count,

                COALESCE(
                    SUM(a.status = 'MAINTENANCE'),
                    0
                ) AS maintenance_count,

                COALESCE(
                    SUM(a.status = 'RETIRED'),
                    0
                ) AS retired_count,

                COALESCE(
                    SUM(a.status = 'LOST'),
                    0
                ) AS lost_count,

                COALESCE(
                    SUM(a.purchase_cost),
                    0
                ) AS total_purchase_cost

            FROM it_assets a

            LEFT JOIN departments d
                ON a.department_id = d.department_id

            GROUP BY
                a.department_id,
                d.department_name

            ORDER BY
                department_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        if owns_connection:
            connection.close()


def get_it_asset_report_data():
    """Read all report sections from one nonlocking InnoDB snapshot."""
    connection = get_connection()
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',
                                     consistent_snapshot=True, readonly=True)
        data = dict(summary=get_it_asset_summary(connection=connection),
                    category_summary=get_it_asset_report_by_category(connection=connection),
                    department_summary=get_it_asset_report_by_department(connection=connection),
                    assets=get_filtered_it_assets(connection=connection))
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT a.asset_id, a.asset_tag, a.status, a.assigned_employee_id,
                       COALESCE(h.active_count, 0) AS active_count, h.employee_id AS history_employee_id,
                       COALESCE(m.open_count, 0) AS open_count
                FROM it_assets a
                LEFT JOIN (
                    SELECT asset_id, COUNT(*) AS active_count, MIN(employee_id) AS employee_id
                    FROM it_asset_assignments WHERE returned_at IS NULL GROUP BY asset_id
                ) h ON h.asset_id = a.asset_id
                LEFT JOIN (
                    SELECT asset_id, COUNT(*) AS open_count
                    FROM it_asset_maintenance WHERE status = 'OPEN' GROUP BY asset_id
                ) m ON m.asset_id = a.asset_id
            """)
            diagnostics = []
            for row in cursor.fetchall():
                issues = []
                custody = row['assigned_employee_id']
                if row['active_count'] != (1 if custody else 0):
                    issues.append('Active assignment count differs from recorded custody')
                elif custody and row['history_employee_id'] != custody:
                    issues.append('Active assignment employee differs from recorded custody')
                if (row['status'] == 'ASSIGNED' and not custody) or (row['status'] == 'AVAILABLE' and custody):
                    issues.append('Asset status differs from recorded custody')
                if row['open_count'] != (1 if row['status'] == 'MAINTENANCE' else 0):
                    issues.append('Open maintenance count differs from asset status')
                if issues:
                    diagnostics.append(dict(asset_id=row['asset_id'], asset_tag=row['asset_tag'], issues=issues))
            data['diagnostics'] = diagnostics
        finally:
            cursor.close()
        connection.commit()
        return data
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
