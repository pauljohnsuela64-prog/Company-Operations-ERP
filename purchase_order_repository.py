import uuid
from database import get_connection



def get_all_purchase_orders():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                po.purchase_order_id,
                po.po_number,
                po.status,
                po.order_date,
                po.expected_delivery_date,
                po.created_at,

                s.supplier_code,
                s.supplier_name,

                pr.request_number,

                u.username AS created_by_username

            FROM purchase_orders po

            JOIN suppliers s
                ON po.supplier_id = s.supplier_id

            JOIN users u
                ON po.created_by = u.user_id

            LEFT JOIN purchase_requests pr
                ON po.request_id = pr.request_id

            ORDER BY
                po.created_at DESC,
                po.purchase_order_id DESC
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def create_purchase_order_from_request(
    request_id,
    supplier_id,
    created_by,
    expected_delivery_date=None,
    notes=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()

        # Lock and verify the purchase request.
        cursor.execute(
            """
            SELECT status
            FROM purchase_requests
            WHERE request_id = %s
            FOR UPDATE
            """,
            (request_id,),
        )

        purchase_request = cursor.fetchone()

        if not purchase_request:
            raise ValueError(
                "Purchase request not found."
            )

        if purchase_request[0] != "APPROVED":
            raise ValueError(
                "Only approved purchase requests can become purchase orders."
            )

        # Prevent creating another active PO
        # for the same purchase request.
        cursor.execute(
            """
            SELECT purchase_order_id
            FROM purchase_orders
            WHERE request_id = %s
              AND status <> 'CANCELLED'
            LIMIT 1
            """,
            (request_id,),
        )

        if cursor.fetchone():
            raise ValueError(
                "A purchase order already exists for this purchase request."
            )

        # Temporary unique number while we wait
        # for MySQL to generate the PO ID.
        temporary_number = (
            f"TEMP-{uuid.uuid4().hex}"
        )

        cursor.execute(
            """
            INSERT INTO purchase_orders (
                po_number,
                request_id,
                supplier_id,
                created_by,
                status,
                order_date,
                expected_delivery_date,
                notes
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                'DRAFT',
                CURRENT_DATE,
                %s,
                %s
            )
            """,
            (
                temporary_number,
                request_id,
                supplier_id,
                created_by,
                expected_delivery_date,
                notes,
            ),
        )

        purchase_order_id = cursor.lastrowid

        po_number = (
            f"PO-{purchase_order_id:06d}"
        )

        cursor.execute(
            """
            UPDATE purchase_orders
            SET po_number = %s
            WHERE purchase_order_id = %s
            """,
            (
                po_number,
                purchase_order_id,
            ),
        )

        # Copy all Purchase Request items
        # into the new Purchase Order.
        cursor.execute(
            """
            INSERT INTO purchase_order_items (
                purchase_order_id,
                request_item_id,
                item_id,
                quantity,
                unit_cost,
                notes
            )
            SELECT
                %s,
                pri.request_item_id,
                pri.item_id,
                pri.quantity,
                COALESCE(
                    pri.estimated_unit_cost,
                    0
                ),
                pri.notes
            FROM purchase_request_items pri
            WHERE pri.request_id = %s
            """,
            (
                purchase_order_id,
                request_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                "Purchase request has no items."
            )

        connection.commit()

        return (
            purchase_order_id,
            po_number,
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_purchase_order_by_id(purchase_order_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                po.purchase_order_id,
                po.po_number,
                po.request_id,
                po.status,
                po.order_date,
                po.expected_delivery_date,
                po.notes,
                po.created_at,

                s.supplier_id,
                s.supplier_code,
                s.supplier_name,

                pr.request_number,

                u.username AS created_by_username

            FROM purchase_orders po

            JOIN suppliers s
                ON po.supplier_id = s.supplier_id

            JOIN users u
                ON po.created_by = u.user_id

            LEFT JOIN purchase_requests pr
                ON po.request_id = pr.request_id

            WHERE po.purchase_order_id = %s
            LIMIT 1
            """,
            (purchase_order_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def get_purchase_order_items(purchase_order_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                poi.purchase_order_item_id,
                poi.request_item_id,
                poi.item_id,
                poi.quantity,
                poi.unit_cost,
                poi.notes,

                i.item_code,
                i.item_name,
                i.unit_of_measure

            FROM purchase_order_items poi

            JOIN inventory_items i
                ON poi.item_id = i.item_id

            WHERE poi.purchase_order_id = %s

            ORDER BY poi.purchase_order_item_id
            """,
            (purchase_order_id,),
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_purchase_order_item_by_id(purchase_order_item_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                purchase_order_item_id,
                purchase_order_id,
                request_item_id,
                item_id,
                quantity,
                unit_cost,
                notes
            FROM purchase_order_items
            WHERE purchase_order_item_id = %s
            LIMIT 1
            """,
            (purchase_order_item_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def update_purchase_order_item_cost(
    purchase_order_item_id,
    unit_cost,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE purchase_order_items
            SET unit_cost = %s
            WHERE purchase_order_item_id = %s
            """,
            (
                unit_cost,
                purchase_order_item_id,
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
# SEND PURCHASE ORDER
# Changes a Purchase Order from DRAFT -> SENT
# ==========================================================

def send_purchase_order(purchase_order_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE purchase_orders
            SET status = 'SENT'
            WHERE purchase_order_id = %s
              AND status = 'DRAFT'
            """,
            (purchase_order_id,),
        )

        # True means exactly one DRAFT PO was updated.
        updated = cursor.rowcount == 1

        connection.commit()

        return updated

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


# ==========================================================
# CANCEL PURCHASE ORDER
#
# A purchase order can only be cancelled when:
#
# 1. Status is DRAFT or SENT
# 2. No goods receipt has been created yet
#
# PARTIALLY_RECEIVED and RECEIVED orders cannot be cancelled.
# ==========================================================

def cancel_purchase_order(purchase_order_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # START TRANSACTION
        # ==================================================

        connection.start_transaction()


        # ==================================================
        # LOCK PURCHASE ORDER
        # ==================================================

        cursor.execute(
            """
            SELECT
                purchase_order_id,
                po_number,
                status
            FROM purchase_orders
            WHERE purchase_order_id = %s
            FOR UPDATE
            """,
            (purchase_order_id,),
        )

        purchase_order = cursor.fetchone()


        # ==================================================
        # VALIDATION - PURCHASE ORDER EXISTS
        # ==================================================

        if not purchase_order:
            raise ValueError(
                "Purchase order not found."
            )


        # ==================================================
        # VALIDATION - STATUS
        # ==================================================

        if purchase_order["status"] == "CANCELLED":
            raise ValueError(
                "Purchase order is already cancelled."
            )

        if purchase_order["status"] not in (
            "DRAFT",
            "SENT",
        ):
            raise ValueError(
                "This purchase order can no longer be cancelled."
            )


        # ==================================================
        # CHECK FOR GOODS RECEIPTS
        # ==================================================

        cursor.execute(
            """
            SELECT receipt_id
            FROM goods_receipts
            WHERE purchase_order_id = %s
            LIMIT 1
            """,
            (purchase_order_id,),
        )

        receipt = cursor.fetchone()


        # ==================================================
        # VALIDATION - RECEIVING ALREADY STARTED
        # ==================================================

        if receipt:
            raise ValueError(
                "This purchase order cannot be cancelled "
                "because receiving has already started."
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        cursor.execute(
            """
            UPDATE purchase_orders
            SET status = 'CANCELLED'
            WHERE purchase_order_id = %s
            """,
            (purchase_order_id,),
        )


        # ==================================================
        # SAVE TRANSACTION
        # ==================================================

        connection.commit()

        return True


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()