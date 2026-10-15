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
    assigned_by,
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

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()
        

# ==========================================================
# UNASSIGN IT ASSET
# ==========================================================

def unassign_it_asset(
    asset_id,
    returned_by,
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
                assigned_employee_id,
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

        if asset["assigned_employee_id"] is None:

            raise ValueError(
                "This asset is not currently assigned."
            )


        # ==================================================
        # CLOSE ACTIVE ASSIGNMENT HISTORY
        # ==========================================================

        cursor.execute(
            """
            UPDATE it_asset_assignments

            SET
                returned_at = CURRENT_TIMESTAMP,
                returned_by = %s

            WHERE
                asset_id = %s
                AND returned_at IS NULL

            ORDER BY assignment_id DESC

            LIMIT 1
            """,
            (
                returned_by,
                asset_id,
            ),
        )


        # ==================================================
        # UPDATE ASSET
        # ==========================================================

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

# ==========================================================
# GET IT ASSET SUMMARY
# ==========================================================

def get_it_asset_summary():
    connection = get_connection()
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
        connection.close()


# ==========================================================
# GET FILTERED IT ASSETS
# ==========================================================

def get_filtered_it_assets(
    search_text=None,
    status=None,
    category_id=None,
    department_id=None,
):
    connection = get_connection()
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

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# IT ASSET REPORT - BY CATEGORY
# ==========================================================

def get_it_asset_report_by_category():
    connection = get_connection()
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
        connection.close()


# ==========================================================
# IT ASSET REPORT - BY DEPARTMENT
# ==========================================================

def get_it_asset_report_by_department():
    connection = get_connection()
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
        connection.close()