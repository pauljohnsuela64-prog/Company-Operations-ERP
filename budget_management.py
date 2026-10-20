"""Budget management filters; financial formulas and eligibility live unchanged."""
from finance_validation import calendar_year,identifier

FIELDS=('department_id','budget_year','budget_amount','notes')


class BudgetError(ValueError):
    def __init__(self,message,status_code=400):
        super().__init__(message)
        self.status_code=status_code


def listing_values(args,default_year):
    keys=('search','year','department_id','page','page_size')
    if any(key not in keys for key in args):raise BudgetError('Unsupported Budget filter.')
    if hasattr(args,'getlist') and any(len(args.getlist(key))>1 for key in keys):raise BudgetError('Submit only one value for each Budget filter.')
    try:
        year=calendar_year(args.get('year',default_year))
        raw=args.get('department_id','')
        department=None if raw in ('',None) else 'none' if raw=='none' else identifier(raw,'Department')
    except ValueError as error:raise BudgetError(str(error)) from None
    search=args.get('search','')
    if not isinstance(search,str) or any(ord(c)<32 or ord(c)==127 for c in search):raise BudgetError('Search must be text without control characters.')
    try:search.encode('utf-8')
    except UnicodeError:raise BudgetError('Search must be valid Unicode.') from None
    search=search.strip()
    if len(search)>100:raise BudgetError('Search must not exceed 100 characters.')
    def number(key,default):
        import re
        raw=str(args.get(key,default))
        if not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:raise BudgetError(f'{key.replace("_"," ").capitalize()} must be a positive integer.')
        return int(raw)
    page=number('page','1');size=number('page_size','25')
    if size not in (25,50,100):raise BudgetError('Page size must be 25, 50 or 100.')
    return dict(year=year,department_id=department,search=search,page=page,page_size=size)


def submitted_values(form):
    if any(len(form.getlist(name))>1 for name in FIELDS):raise BudgetError('Submit only one value for each Budget field.')
    return [form.get(name,'') for name in FIELDS]
