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
    connection = get_connection()
    cursor = connection.cursor()

    try:

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

        connection.commit()

        return cursor.lastrowid

    except Exception:

        connection.rollback()
        raise

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
    connection = get_connection()
    cursor = connection.cursor()

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT asset_id
            FROM it_assets
            WHERE asset_id = %s
            FOR UPDATE
            """,
            (asset_id,),
        )

        if not cursor.fetchone():
            raise ValueError(
                "IT asset was not found."
            )

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

    except Exception:

        connection.rollback()
        raise

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
):
    connection = get_connection()
    cursor = connection.cursor()

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

        if asset[1] in (
            "RETIRED",
            "LOST",
        ):
            raise ValueError(
                "Retired or lost assets cannot be assigned."
            )

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

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# UNASSIGN IT ASSET
# ==========================================================

def unassign_it_asset(asset_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:

        connection.start_transaction()

        cursor.execute(
            """
            SELECT asset_id
            FROM it_assets
            WHERE asset_id = %s
            FOR UPDATE
            """,
            (asset_id,),
        )

        if not cursor.fetchone():
            raise ValueError(
                "IT asset was not found."
            )

        cursor.execute(
            """
            UPDATE it_assets
            SET
                assigned_employee_id = NULL,
                status = 'AVAILABLE'

            WHERE asset_id = %s
            """,
            (asset_id,),
        )

        connection.commit()

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

    except Exception:

        connection.rollback()
        raise

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
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        connection.start_transaction()


        # ==================================================
        # LOCK MAINTENANCE RECORD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                maintenance_id,
                asset_id,
                status

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

        if maintenance["status"] != "OPEN":

            raise ValueError(
                "Only open maintenance records "
                "can be completed."
            )


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

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()