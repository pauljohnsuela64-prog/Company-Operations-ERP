from procurement_validation import lock_active_inventory_item
import uuid

from database import get_connection
from procurement_validation import decimal_value, validate_notes, lock_draft, lock_item_parent


def get_all_purchase_requests():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                pr.request_id,
                pr.request_number,
                pr.purpose,
                pr.status,
                pr.submitted_at,
                pr.approved_at,
                pr.created_at,

                u.username AS requested_by_username,

                d.department_code,
                d.department_name

            FROM purchase_requests pr

            JOIN users u
                ON pr.requested_by = u.user_id

            LEFT JOIN departments d
                ON pr.department_id = d.department_id

            ORDER BY
                pr.created_at DESC,
                pr.request_id DESC
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def create_purchase_request(
    requested_by,
    department_id,
    purpose,
):
    validate_notes(purpose, "Purchase request purpose")
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()

        temporary_number = (
            f"TEMP-{uuid.uuid4().hex}"
        )

        cursor.execute(
            """
            INSERT INTO purchase_requests (
                request_number,
                requested_by,
                department_id,
                purpose,
                status
            )
            VALUES (%s, %s, %s, %s, 'DRAFT')
            """,
            (
                temporary_number,
                requested_by,
                department_id,
                purpose,
            ),
        )

        request_id = cursor.lastrowid

        request_number = (
            f"PR-{request_id:06d}"
        )

        cursor.execute(
            """
            UPDATE purchase_requests
            SET request_number = %s
            WHERE request_id = %s
            """,
            (
                request_number,
                request_id,
            ),
        )

        connection.commit()

        return request_id, request_number

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_purchase_request_by_id(request_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                pr.request_id,
                pr.request_number,
                pr.purpose,
                pr.status,
                pr.submitted_at,
                pr.approved_at,
                pr.rejection_reason,
                pr.created_at,

                u.username AS requested_by_username,

                d.department_code,
                d.department_name,

                approver.username AS approved_by_username

            FROM purchase_requests pr

            JOIN users u
                ON pr.requested_by = u.user_id

            LEFT JOIN departments d
                ON pr.department_id = d.department_id

            LEFT JOIN users approver
                ON pr.approved_by = approver.user_id

            WHERE pr.request_id = %s
            LIMIT 1
            """,
            (request_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def get_purchase_request_items(request_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                pri.request_item_id,
                pri.quantity,
                pri.estimated_unit_cost,
                pri.notes,

                i.item_code,
                i.item_name,
                i.unit_of_measure

            FROM purchase_request_items pri

            JOIN inventory_items i
                ON pri.item_id = i.item_id

            WHERE pri.request_id = %s

            ORDER BY pri.request_item_id
            """,
            (request_id,),
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def add_purchase_request_item(
    request_id,
    item_id,
    quantity,
    estimated_unit_cost=None,
    notes=None,
):
    quantity = decimal_value(quantity, "Quantity", positive=True)
    if estimated_unit_cost is not None:
        estimated_unit_cost = decimal_value(estimated_unit_cost, "Estimated unit cost")
    validate_notes(notes, "Item notes")
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        lock_draft(cursor, "purchase_requests", "request_id", request_id)
        lock_active_inventory_item(cursor, item_id)
        cursor.execute(
            """
            INSERT INTO purchase_request_items (
                request_id,
                item_id,
                quantity,
                estimated_unit_cost,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                request_id,
                item_id,
                quantity,
                estimated_unit_cost,
                notes,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_purchase_request_item_by_id(request_item_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                request_item_id,
                request_id,
                item_id,
                quantity,
                estimated_unit_cost,
                notes
            FROM purchase_request_items
            WHERE request_item_id = %s
            LIMIT 1
            """,
            (request_item_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def update_purchase_request_item(
    request_item_id,
    item_id,
    quantity,
    estimated_unit_cost=None,
    notes=None,
):
    quantity = decimal_value(quantity, "Quantity", positive=True)
    if estimated_unit_cost is not None:
        estimated_unit_cost = decimal_value(estimated_unit_cost, "Estimated unit cost")
    validate_notes(notes, "Item notes")
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        lock_item_parent(cursor, "purchase_request_items", "request_item_id", request_item_id, "purchase_requests", "request_id")
        lock_active_inventory_item(cursor, item_id)
        cursor.execute(
            """
            UPDATE purchase_request_items
            SET
                item_id = %s,
                quantity = %s,
                estimated_unit_cost = %s,
                notes = %s
            WHERE request_item_id = %s
            """,
            (
                item_id,
                quantity,
                estimated_unit_cost,
                notes,
                request_item_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def delete_purchase_request_item(request_item_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        lock_item_parent(cursor, "purchase_request_items", "request_item_id", request_item_id, "purchase_requests", "request_id")
        cursor.execute(
            """
            DELETE FROM purchase_request_items
            WHERE request_item_id = %s
            """,
            (request_item_id,),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def submit_purchase_request(request_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        cursor.execute("SELECT status FROM purchase_requests WHERE request_id = %s FOR UPDATE", (request_id,))
        parent = cursor.fetchone()
        if not parent or parent[0] != "DRAFT":
            connection.rollback()
            return False
        # Recheck after acquiring the same lock used by item deletion.
        cursor.execute("SELECT COUNT(*) FROM purchase_request_items WHERE request_id = %s", (request_id,))
        if cursor.fetchone()[0] == 0:
            connection.rollback()
            return False
        cursor.execute(
            """
            UPDATE purchase_requests
            SET
                status = 'SUBMITTED',
                submitted_at = CURRENT_TIMESTAMP
            WHERE request_id = %s
              AND status = 'DRAFT'
            """,
            (request_id,),
        )

        updated = cursor.rowcount == 1

        connection.commit()

        return updated

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



def approve_purchase_request(
    request_id,
    approved_by,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE purchase_requests
            SET
                status = 'APPROVED',
                approved_by = %s,
                approved_at = CURRENT_TIMESTAMP,
                rejection_reason = NULL
            WHERE request_id = %s
              AND status = 'SUBMITTED'
            """,
            (
                approved_by,
                request_id,
            ),
        )

        updated = cursor.rowcount == 1

        connection.commit()

        return updated

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def reject_purchase_request(
    request_id,
    rejection_reason,
):
    validate_notes(rejection_reason, "Rejection reason")
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE purchase_requests
            SET
                status = 'REJECTED',
                rejection_reason = %s,
                approved_by = NULL,
                approved_at = NULL
            WHERE request_id = %s
              AND status = 'SUBMITTED'
            """,
            (
                rejection_reason,
                request_id,
            ),
        )

        updated = cursor.rowcount == 1

        connection.commit()

        return updated

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()