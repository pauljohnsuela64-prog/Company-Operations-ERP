"""Consistent Finance report aggregates from one filtered expense SELECT."""
from calendar import month_name
from decimal import Decimal

from expense_repository import get_filtered_expenses
from finance_validation import calendar_year, identifier

STATUSES = ('DRAFT', 'APPROVED', 'PAID', 'CANCELLED')


def filters(args, default_year=None):
    result = dict(year=default_year, status=None, category_id=None, department_id=None,
                  search_text=args.get('search', '').strip() or None)
    if args.get('year', '').strip():
        try: result['year'] = calendar_year(args['year'].strip())
        except ValueError: pass
    status = args.get('status', '').strip().upper()
    if status in STATUSES: result['status'] = status
    for key in ('category_id', 'department_id'):
        value = args.get(key, '').strip()
        if key == 'department_id' and value == 'none':
            result[key] = 'none'
        elif value:
            try: result[key] = identifier(value, key.replace('_', ' '))
            except ValueError: pass
    return result


def report(selected):
    records = get_filtered_expenses(**selected)
    summary = dict(total_expenses=len(records), total_amount=Decimal('0.00'))
    for status in STATUSES:
        summary[status.lower()+'_count'] = 0
        summary[status.lower()+'_amount'] = Decimal('0.00')
    months, categories = {}, {}
    for row in records:
        amount = Decimal(row['amount'])
        summary['total_amount'] += amount
        # Preserve SQL CASE semantics if historical non-strict SQL produced an
        # invalid ENUM value: keep the detail/total, do not invent a valid state.
        if row['status'] not in STATUSES: continue
        status = row['status'].lower()
        summary[status+'_count'] += 1
        summary[status+'_amount'] += amount
        if status != 'paid': continue
        month = row['expense_date'].month
        bucket = months.setdefault(month, dict(month_number=month, month_name=month_name[month],
                                               expense_count=0, total_amount=Decimal('0.00')))
        bucket['expense_count'] += 1; bucket['total_amount'] += amount
        category = categories.setdefault(row['category_id'], dict(category_id=row['category_id'],
            category_code=row['category_code'], category_name=row['category_name'],
            expense_count=0, total_amount=Decimal('0.00')))
        category['expense_count'] += 1; category['total_amount'] += amount
    return dict(summary=summary, monthly_expenses=[months[m] for m in sorted(months)],
                category_expenses=sorted(categories.values(), key=lambda c: (-c['total_amount'], c['category_name'])),
                expense_records=records)
