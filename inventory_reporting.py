"""Read-only, paginated Inventory reports. No stock writes or corrections."""
from datetime import date, datetime, time
from decimal import localcontext
import re
from database import get_connection

MOVEMENT_TYPES = ('IN', 'OUT', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT')


def report_filters(args, movements=True):
    result = {}
    for name in ('item_id', 'warehouse_id', 'page', 'page_size'):
        raw = args.get(name, '')
        if raw == '' or raw is None:
            result[name] = {'page': 1, 'page_size': 50}.get(name)
            continue
        if not str(raw).isascii() or not str(raw).isdigit():
            raise ValueError(f"{name.replace('_', ' ').capitalize()} must be a positive integer.")
        value = int(raw)
        maximum = 100 if name == 'page_size' else 2147483647
        if not 1 <= value <= maximum:
            raise ValueError(f"{name.replace('_', ' ').capitalize()} must be between 1 and {maximum}.")
        result[name] = value
    if movements:
        kind = args.get('movement_type', '') or ''
        if kind and kind not in MOVEMENT_TYPES:
            raise ValueError('Select a valid movement type.')
        result['movement_type'] = kind
        result['q'] = (args.get('q', '') or '').strip()
        if len(result['q']) > 200:
            raise ValueError('Search cannot exceed 200 characters.')
        dates = {}
        for name in ('date_from', 'date_to'):
            raw = args.get(name, '') or ''
            if raw:
                try:
                    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw):
                        raise ValueError
                    dates[name] = date.fromisoformat(raw)
                except ValueError:
                    raise ValueError('Enter valid dates in YYYY-MM-DD format.') from None
            result[name] = raw
        if len(dates) == 2 and dates['date_from'] > dates['date_to']:
            raise ValueError('Start date must not be after end date.')
    return result


def _page(select_sql, from_sql, where_sql, params, order_sql, page, page_size):
    connection = get_connection()
    cursor = None
    try:
        # COUNT and displayed rows see the same snapshot, even while stock changes.
        connection.start_transaction(isolation_level='REPEATABLE READ', consistent_snapshot=True, readonly=True)
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS total ' + from_sql + where_sql, tuple(params))
        total = cursor.fetchone()['total']
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        cursor.execute(select_sql + from_sql + where_sql + order_sql + ' LIMIT %s OFFSET %s',
                       tuple(params) + (page_size, (page - 1) * page_size))
        return dict(rows=cursor.fetchall(), total=total, page=page, pages=pages, page_size=page_size)
    finally:
        try:
            connection.rollback()  # End the read-only snapshot; never commit a business write.
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                connection.close()


def get_movement_page(**filters):
    filters = report_filters(filters)
    joins = ''' FROM stock_movements sm
        JOIN inventory_items i ON i.item_id=sm.item_id
        JOIN warehouses w ON w.warehouse_id=sm.warehouse_id
        LEFT JOIN users u ON u.user_id=sm.created_by
        LEFT JOIN goods_receipts gr ON sm.reference_type='GOODS_RECEIPT'
          AND gr.receipt_id=sm.reference_id AND gr.warehouse_id=sm.warehouse_id
          AND EXISTS (SELECT 1 FROM goods_receipt_items gri
              JOIN purchase_order_items poi ON poi.purchase_order_item_id=gri.purchase_order_item_id
              WHERE gri.receipt_id=gr.receipt_id AND poi.item_id=sm.item_id)
    '''
    clauses, params = [], []
    for name in ('item_id', 'warehouse_id', 'movement_type'):
        if filters.get(name):
            clauses.append(f'sm.{name}=%s'); params.append(filters[name])
    for name, operator, clock in (('date_from', '>=', time.min), ('date_to', '<=', time.max)):
        if filters[name]:
            clauses.append(f'sm.created_at {operator} %s')
            params.append(datetime.combine(date.fromisoformat(filters[name]), clock))
    if filters['q']:
        pattern = '%' + filters['q'].replace('=', '==').replace('%', '=%').replace('_', '=_') + '%'
        columns = ('i.item_code','i.item_name','w.warehouse_code','w.warehouse_name',
                   'sm.notes','sm.reference_type','CAST(sm.reference_id AS CHAR)',
                   'u.username','gr.receipt_number')
        clauses.append('(' + ' OR '.join(column + " LIKE %s ESCAPE '='" for column in columns) + ')')
        params.extend([pattern] * len(columns))
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    select = '''SELECT sm.movement_id, sm.item_id, sm.warehouse_id, sm.movement_type,
        sm.quantity, sm.reference_type, sm.reference_id, sm.notes, sm.created_at,
        i.item_code,i.item_name,i.unit_of_measure,w.warehouse_code,w.warehouse_name,
        u.username AS created_by_username,gr.receipt_id AS source_receipt_id,gr.receipt_number '''
    return _page(select, joins, where, params, ' ORDER BY sm.created_at DESC,sm.movement_id DESC',
                 filters['page'], filters['page_size'])


def get_reconciliation_page(**filters):
    filters = report_filters(filters, movements=False)
    # No warehouse/item cross-product: compare only pairs with a balance or movement.
    joins = ''' FROM (
            SELECT item_id,warehouse_id FROM inventory_stock
            UNION SELECT item_id,warehouse_id FROM stock_movements
        ) pairs
        LEFT JOIN inventory_stock s ON s.item_id=pairs.item_id AND s.warehouse_id=pairs.warehouse_id
        LEFT JOIN inventory_items i ON i.item_id=pairs.item_id
        LEFT JOIN warehouses w ON w.warehouse_id=pairs.warehouse_id
        LEFT JOIN (
            SELECT item_id,warehouse_id,COUNT(*) AS movement_count,
              MIN(created_at) AS first_movement_at,
              SUM(CASE WHEN movement_type IN ('IN','ADJUSTMENT_IN') THEN quantity
                       WHEN movement_type IN ('OUT','ADJUSTMENT_OUT') THEN -quantity ELSE 0 END) AS movement_balance,
              SUM(CASE WHEN quantity IS NULL OR quantity<=0 OR movement_type IS NULL
                         OR movement_type NOT IN ('IN','OUT','ADJUSTMENT_IN','ADJUSTMENT_OUT')
                       THEN 1 ELSE 0 END) AS unsupported_count
            FROM stock_movements GROUP BY item_id,warehouse_id
        ) ledger ON ledger.item_id=pairs.item_id AND ledger.warehouse_id=pairs.warehouse_id
    '''
    clauses, params = [], []
    for name in ('item_id', 'warehouse_id'):
        if filters[name]:
            clauses.append(f'pairs.{name}=%s'); params.append(filters[name])
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    select = '''SELECT pairs.item_id,pairs.warehouse_id,i.item_code,i.item_name,i.unit_of_measure,
        w.warehouse_code,w.warehouse_name,s.quantity,s.item_id IS NOT NULL AS has_balance,
        COALESCE(ledger.movement_count,0) AS movement_count,ledger.first_movement_at,
        ledger.movement_balance,COALESCE(ledger.unsupported_count,0) AS unsupported_count '''
    result = _page(select, joins, where, params, ' ORDER BY pairs.item_id,pairs.warehouse_id',
                   filters['page'], filters['page_size'])
    for row in result['rows']:
        row['difference'] = None
        if row['has_balance'] and (row['quantity'] is None or row['quantity'] < 0):
            row['comparison'] = 'Invalid stored balance ? review required'
        elif row['unsupported_count'] or row['item_code'] is None or row['warehouse_code'] is None:
            row['comparison'] = 'Unsupported history — cannot compare'
        elif not row['has_balance']:
            row['comparison'] = 'Missing balance record — review required'
        elif not row['movement_count']:
            row['comparison'] = 'No recorded movements — opening balance unknown'
        else:
            with localcontext() as context:
                context.prec = 65
                row['difference'] = row['quantity'] - row['movement_balance']
            row['comparison'] = ('Matches recorded history — coverage unverified' if row['difference'] == 0
                                 else 'Difference — history coverage unverified')
    return result
