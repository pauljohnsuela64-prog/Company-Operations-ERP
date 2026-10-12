from database import get_connection


def get_all_stock():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                s.item_id,
                s.warehouse_id,
                s.quantity,

                i.item_code,
                i.item_name,
                i.unit_of_measure,
                i.reorder_level,

                w.warehouse_code,
                w.warehouse_name

            FROM inventory_stock s

            JOIN inventory_items i
                ON s.item_id = i.item_id

            JOIN warehouses w
                ON s.warehouse_id = w.warehouse_id

            ORDER BY
                i.item_name,
                w.warehouse_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def stock_in(
    item_id,
    warehouse_id,
    quantity,
    notes,
    created_by,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

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

        if stock:
            cursor.execute(
                """
                UPDATE inventory_stock
                SET quantity = quantity + %s
                WHERE item_id = %s
                  AND warehouse_id = %s
                """,
                (
                    quantity,
                    item_id,
                    warehouse_id,
                ),
            )

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
                    quantity,
                ),
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
                'MANUAL_STOCK_IN',
                NULL,
                %s,
                %s
            )
            """,
            (
                item_id,
                warehouse_id,
                quantity,
                notes,
                created_by,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



def stock_out(
    item_id,
    warehouse_id,
    quantity,
    notes,
    created_by,
):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

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

        if not stock:
            raise ValueError(
                "No stock exists for this item in the selected warehouse."
            )

        if quantity > stock["quantity"]:
            raise ValueError(
                "Insufficient stock. Stock cannot go below zero."
            )

        cursor.execute(
            """
            UPDATE inventory_stock
            SET quantity = quantity - %s
            WHERE item_id = %s
              AND warehouse_id = %s
            """,
            (
                quantity,
                item_id,
                warehouse_id,
            ),
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
                'OUT',
                %s,
                'MANUAL_STOCK_OUT',
                NULL,
                %s,
                %s
            )
            """,
            (
                item_id,
                warehouse_id,
                quantity,
                notes,
                created_by,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



def get_stock_movements():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                sm.movement_id,
                sm.movement_type,
                sm.quantity,
                sm.reference_type,
                sm.notes,
                sm.created_at,

                i.item_code,
                i.item_name,
                i.unit_of_measure,

                w.warehouse_code,
                w.warehouse_name,

                u.username AS created_by_username

            FROM stock_movements sm

            JOIN inventory_items i
                ON sm.item_id = i.item_id

            JOIN warehouses w
                ON sm.warehouse_id = w.warehouse_id

            LEFT JOIN users u
                ON sm.created_by = u.user_id

            ORDER BY
                sm.created_at DESC,
                sm.movement_id DESC
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()