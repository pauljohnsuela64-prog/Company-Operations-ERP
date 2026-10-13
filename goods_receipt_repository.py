# ==========================================================
# IMPORTS
# ==========================================================

import uuid
from decimal import Decimal, InvalidOperation

from database import get_connection


# ==========================================================
# GET PURCHASE ORDERS AVAILABLE FOR RECEIVING
#
# Only SENT or PARTIALLY_RECEIVED purchase orders
# should be available for goods receiving.
# ==========================================================

def get_receivable_purchase_orders():
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

                s.supplier_code,
                s.supplier_name

            FROM purchase_orders po

            JOIN suppliers s
                ON po.supplier_id = s.supplier_id

            WHERE po.status IN (
                'SENT',
                'PARTIALLY_RECEIVED'
            )

            ORDER BY
                po.order_date DESC,
                po.purchase_order_id DESC
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


# ==========================================================
# GET ONE RECEIVABLE PURCHASE ORDER
#
# Only SENT or PARTIALLY_RECEIVED purchase orders
# are allowed here.
# ==========================================================

def get_receivable_purchase_order_by_id(purchase_order_id):
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
                po.notes,

                s.supplier_id,
                s.supplier_code,
                s.supplier_name

            FROM purchase_orders po

            JOIN suppliers s
                ON po.supplier_id = s.supplier_id

            WHERE po.purchase_order_id = %s
              AND po.status IN (
                  'SENT',
                  'PARTIALLY_RECEIVED'
              )

            LIMIT 1
            """,
            (purchase_order_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


# ==========================================================
# GET PURCHASE ORDER ITEMS STILL WAITING TO BE RECEIVED
#
# Example:
#
# Ordered:          20 keyboards
# Already received: 5 keyboards
# Remaining:        15 keyboards
# ==========================================================

def get_receivable_purchase_order_items(purchase_order_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                poi.purchase_order_item_id,
                poi.item_id,
                poi.quantity AS ordered_quantity,
                poi.unit_cost,

                i.item_code,
                i.item_name,
                i.unit_of_measure,

                COALESCE(
                    SUM(gri.quantity_received),
                    0
                ) AS received_quantity,

                (
                    poi.quantity
                    -
                    COALESCE(
                        SUM(gri.quantity_received),
                        0
                    )
                ) AS remaining_quantity

            FROM purchase_order_items poi

            JOIN inventory_items i
                ON poi.item_id = i.item_id

            LEFT JOIN goods_receipt_items gri
                ON gri.purchase_order_item_id
                = poi.purchase_order_item_id

            WHERE poi.purchase_order_id = %s

            GROUP BY
                poi.purchase_order_item_id,
                poi.item_id,
                poi.quantity,
                poi.unit_cost,
                i.item_code,
                i.item_name,
                i.unit_of_measure

            HAVING remaining_quantity > 0

            ORDER BY
                poi.purchase_order_item_id
            """,
            (purchase_order_id,),
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()



# ==========================================================
# CREATE GOODS RECEIPT
#
# This is one database transaction.
#
# It will:
# 1. Validate the Purchase Order
# 2. Validate the warehouse
# 3. Validate received quantities
# 4. Create the Goods Receipt
# 5. Create Goods Receipt Items
# 6. Increase Inventory Stock
# 7. Create Stock Movement history
# 8. Update PO status
#
# If ANY step fails:
# everything is rolled back.
# ==========================================================

def create_goods_receipt(
    purchase_order_id,
    warehouse_id,
    received_by,
    received_items,
    notes=None,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ==================================================
        # START TRANSACTION
        # ==================================================

        connection.start_transaction()


        # ==================================================
        # 1. LOCK AND VALIDATE PURCHASE ORDER
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

        if not purchase_order:
            raise ValueError(
                "Purchase order not found."
            )

        if purchase_order["status"] not in (
            "SENT",
            "PARTIALLY_RECEIVED",
        ):
            raise ValueError(
                "This purchase order is not available for receiving."
            )


        # ==================================================
        # 2. VALIDATE WAREHOUSE
        # ==================================================

        cursor.execute(
            """
            SELECT
                warehouse_id,
                warehouse_code,
                warehouse_name
            FROM warehouses
            WHERE warehouse_id = %s
              AND is_active = TRUE
            LIMIT 1
            """,
            (warehouse_id,),
        )

        warehouse = cursor.fetchone()

        if not warehouse:
            raise ValueError(
                "Selected warehouse is invalid or inactive."
            )


        # ==================================================
        # 3. GET PO ITEMS + ALREADY RECEIVED QUANTITIES
        # ==================================================

        cursor.execute(
            """
            SELECT
                poi.purchase_order_item_id,
                poi.item_id,
                poi.quantity AS ordered_quantity,

                COALESCE(
                    SUM(gri.quantity_received),
                    0
                ) AS received_quantity

            FROM purchase_order_items poi

            LEFT JOIN goods_receipt_items gri
                ON gri.purchase_order_item_id
                = poi.purchase_order_item_id

            WHERE poi.purchase_order_id = %s

            GROUP BY
                poi.purchase_order_item_id,
                poi.item_id,
                poi.quantity
            """,
            (purchase_order_id,),
        )

        po_items = cursor.fetchall()

        if not po_items:
            raise ValueError(
                "Purchase order has no items."
            )


        # ==================================================
        # CREATE LOOKUP
        #
        # Example:
        #
        # {
        #     1: {
        #         item_id: 5,
        #         ordered_quantity: 20,
        #         received_quantity: 5
        #     }
        # }
        # ==================================================

        po_item_lookup = {
            item["purchase_order_item_id"]: item
            for item in po_items
        }


        # ==================================================
        # VALIDATE RECEIVED ITEMS
        #
        # received_items should look like:
        #
        # {
        #     purchase_order_item_id: quantity_received
        # }
        #
        # Example:
        #
        # {
        #     1: Decimal("5")
        # }
        # ==================================================

        valid_received_items = []

        for purchase_order_item_id, quantity in received_items.items():

            try:
                purchase_order_item_id = int(
                    purchase_order_item_id
                )

                quantity_received = Decimal(
                    str(quantity)
                )

            except (
                ValueError,
                TypeError,
                InvalidOperation,
            ):
                raise ValueError(
                    "Invalid received quantity."
                )


            # Ignore zero quantities

            if quantity_received == 0:
                continue


            # Negative quantities are never allowed

            if quantity_received < 0:
                raise ValueError(
                    "Received quantity cannot be negative."
                )


            # Make sure item belongs to this PO

            po_item = po_item_lookup.get(
                purchase_order_item_id
            )

            if not po_item:
                raise ValueError(
                    "Invalid purchase order item."
                )


            ordered_quantity = Decimal(
                str(po_item["ordered_quantity"])
            )

            already_received = Decimal(
                str(po_item["received_quantity"])
            )

            remaining_quantity = (
                ordered_quantity
                -
                already_received
            )


            # Do not receive more than was ordered

            if quantity_received > remaining_quantity:
                raise ValueError(
                    "Received quantity cannot exceed the remaining quantity."
                )


            valid_received_items.append(
                {
                    "purchase_order_item_id":
                        purchase_order_item_id,

                    "item_id":
                        po_item["item_id"],

                    "quantity_received":
                        quantity_received,
                }
            )


        # At least one item must be received

        if not valid_received_items:
            raise ValueError(
                "Enter a received quantity for at least one item."
            )


        # ==================================================
        # VALIDATE NOTES LENGTH
        # goods_receipts.notes = VARCHAR(255)
        # ==================================================

        if notes and len(notes) > 255:
            raise ValueError(
                "Receipt notes cannot exceed 255 characters."
            )


        # ==================================================
        # 4. CREATE GOODS RECEIPT
        #
        # We use a temporary unique number first.
        # After MySQL gives us receipt_id,
        # we create:
        #
        # GR-000001
        # GR-000002
        # etc.
        # ==================================================

        temporary_number = (
            f"TEMP-{uuid.uuid4().hex}"
        )

        cursor.execute(
            """
            INSERT INTO goods_receipts (
                receipt_number,
                purchase_order_id,
                warehouse_id,
                received_by,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                temporary_number,
                purchase_order_id,
                warehouse_id,
                received_by,
                notes,
            ),
        )

        receipt_id = cursor.lastrowid

        receipt_number = (
            f"GR-{receipt_id:06d}"
        )


        # Replace temporary number with real number

        cursor.execute(
            """
            UPDATE goods_receipts
            SET receipt_number = %s
            WHERE receipt_id = %s
            """,
            (
                receipt_number,
                receipt_id,
            ),
        )


        # ==================================================
        # 5. PROCESS EACH RECEIVED ITEM
        # ==================================================

        for received_item in valid_received_items:

            purchase_order_item_id = (
                received_item[
                    "purchase_order_item_id"
                ]
            )

            item_id = received_item["item_id"]

            quantity_received = (
                received_item[
                    "quantity_received"
                ]
            )


            # ==============================================
            # CREATE GOODS RECEIPT ITEM
            # ==============================================

            cursor.execute(
                """
                INSERT INTO goods_receipt_items (
                    receipt_id,
                    purchase_order_item_id,
                    quantity_received
                )
                VALUES (%s, %s, %s)
                """,
                (
                    receipt_id,
                    purchase_order_item_id,
                    quantity_received,
                ),
            )


            # ==============================================
            # 6. LOCK CURRENT INVENTORY STOCK
            # ==============================================

            cursor.execute(
                """
                SELECT quantity
                FROM inventory_stock
                WHERE item_id = %s
                  AND warehouse_id = %s
                FOR UPDATE
                """,
                (
                    item_id,
                    warehouse_id,
                ),
            )

            stock = cursor.fetchone()


            # ==============================================
            # STOCK ALREADY EXISTS
            # Increase existing quantity
            # ==============================================

            if stock:

                cursor.execute(
                    """
                    UPDATE inventory_stock
                    SET quantity = quantity + %s
                    WHERE item_id = %s
                      AND warehouse_id = %s
                    """,
                    (
                        quantity_received,
                        item_id,
                        warehouse_id,
                    ),
                )


            # ==============================================
            # STOCK DOES NOT EXIST
            # Create new item/warehouse stock row
            # ==============================================

            else:

                cursor.execute(
                    """
                    INSERT INTO inventory_stock (
                        item_id,
                        warehouse_id,
                        quantity
                    )
                    VALUES (%s, %s, %s)
                    """,
                    (
                        item_id,
                        warehouse_id,
                        quantity_received,
                    ),
                )


            # ==============================================
            # 7. CREATE STOCK MOVEMENT HISTORY
            #
            # reference_type = GOODS_RECEIPT
            # reference_id   = receipt_id
            #
            # This lets us know WHY inventory increased.
            # ==============================================

            movement_notes = (
                f"Received from "
                f"{purchase_order['po_number']} "
                f"via {receipt_number}"
            )

            if notes:
                movement_notes += (
                    f" - {notes}"
                )

            cursor.execute(
                """
                INSERT INTO stock_movements (
                    item_id,
                    warehouse_id,
                    movement_type,
                    quantity,
                    reference_type,
                    reference_id,
                    notes,
                    created_by
                )
                VALUES (
                    %s,
                    %s,
                    'IN',
                    %s,
                    'GOODS_RECEIPT',
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    item_id,
                    warehouse_id,
                    quantity_received,
                    receipt_id,
                    movement_notes,
                    received_by,
                ),
            )


        # ==================================================
        # 8. CHECK IF PO STILL HAS ITEMS REMAINING
        # ==================================================

        cursor.execute(
            """
            SELECT COUNT(*) AS remaining_items

            FROM purchase_order_items poi

            WHERE poi.purchase_order_id = %s

              AND poi.quantity > (
                    SELECT COALESCE(
                        SUM(gri.quantity_received),
                        0
                    )

                    FROM goods_receipt_items gri

                    WHERE
                        gri.purchase_order_item_id
                        =
                        poi.purchase_order_item_id
              )
            """,
            (purchase_order_id,),
        )

        result = cursor.fetchone()

        remaining_items = result[
            "remaining_items"
        ]


        # ==================================================
        # UPDATE PURCHASE ORDER STATUS
        #
        # Items still remaining:
        # PARTIALLY_RECEIVED
        #
        # Everything received:
        # RECEIVED
        # ==================================================

        if remaining_items > 0:
            new_status = "PARTIALLY_RECEIVED"
        else:
            new_status = "RECEIVED"


        cursor.execute(
            """
            UPDATE purchase_orders
            SET status = %s
            WHERE purchase_order_id = %s
            """,
            (
                new_status,
                purchase_order_id,
            ),
        )


        # ==================================================
        # EVERYTHING WORKED
        # COMMIT TRANSACTION
        # ==================================================

        connection.commit()

        return (
            receipt_id,
            receipt_number,
            new_status,
        )


    # ======================================================
    # SOMETHING FAILED
    # ROLLBACK EVERYTHING
    # ======================================================

    except Exception:

        connection.rollback()
        raise


    # ======================================================
    # ALWAYS CLOSE DATABASE CONNECTION
    # ======================================================

    finally:

        cursor.close()
        connection.close()



# ==========================================================
# GET ALL GOODS RECEIPTS
#
# Used for the Goods Receipt History page.
#
# Shows:
# - Receipt number
# - Purchase Order
# - Supplier
# - Warehouse
# - Who received it
# - Date received
# - Total quantity received
# ==========================================================

def get_all_goods_receipts():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute(
            """
            SELECT
                gr.receipt_id,
                gr.receipt_number,
                gr.purchase_order_id,
                gr.received_at,
                gr.notes,
                gr.created_at,

                po.po_number,

                s.supplier_code,
                s.supplier_name,

                w.warehouse_code,
                w.warehouse_name,

                u.username AS received_by_username,

                COALESCE(
                    SUM(gri.quantity_received),
                    0
                ) AS total_quantity_received

            FROM goods_receipts gr

            JOIN purchase_orders po
                ON gr.purchase_order_id
                = po.purchase_order_id

            JOIN suppliers s
                ON po.supplier_id
                = s.supplier_id

            JOIN warehouses w
                ON gr.warehouse_id
                = w.warehouse_id

            LEFT JOIN users u
                ON gr.received_by
                = u.user_id

            LEFT JOIN goods_receipt_items gri
                ON gr.receipt_id
                = gri.receipt_id

            GROUP BY
                gr.receipt_id,
                gr.receipt_number,
                gr.purchase_order_id,
                gr.received_at,
                gr.notes,
                gr.created_at,

                po.po_number,

                s.supplier_code,
                s.supplier_name,

                w.warehouse_code,
                w.warehouse_name,

                u.username

            ORDER BY
                gr.received_at DESC,
                gr.receipt_id DESC
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()