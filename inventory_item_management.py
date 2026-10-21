"""Inventory Items input and listing contract; no stock or receiving policy."""
import re

FIELDS=('item_code','item_name','category_id','description','unit_of_measure','reorder_level')


class ItemError(ValueError):
    def __init__(self,message,status_code=400):
        super().__init__(message)
        self.status_code=status_code


def identifier(value):
    raw=str(value).strip()
    if isinstance(value,bool) or not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:
        raise ItemError('Select a valid inventory item.')
    return int(raw)


def validate_text(value,label,multiline=False):
    if value is None:return
    if not isinstance(value,str):raise ItemError(f'{label} must be text.')
    if any((ord(c)<32 and not (multiline and c in '\t\r\n')) or ord(c)==127 for c in value):
        raise ItemError(f'{label} contains unsupported control characters.')
    try:value.encode('utf-8')
    except UnicodeError:raise ItemError(f'{label} must be valid Unicode.') from None


def submitted_values(form):
    if any(len(form.getlist(name))>1 for name in FIELDS):raise ItemError('Submit only one value for each item field.')
    return [form.get(name,'0' if name=='reorder_level' else '') for name in FIELDS]


def filters(args):
    keys=('search','category_id','status','page','page_size')
    if any(key not in keys for key in args):raise ItemError('Unsupported item filter.')
    if hasattr(args,'getlist') and any(len(args.getlist(key))>1 for key in keys):raise ItemError('Submit only one value for each item filter.')
    search=args.get('search','');validate_text(search,'Search')
    if not isinstance(search,str):raise ItemError('Search must be text.')
    search=search.strip()
    if len(search)>100:raise ItemError('Search cannot exceed 100 characters.')
    category=args.get('category_id','')
    if category not in ('','none'):
        from inventory_validation import category_identifier
        try:category=category_identifier(category)
        except ValueError as error:raise ItemError(str(error)) from None
        if category is None:raise ItemError('Select a valid inventory category.')
    status=args.get('status','')
    if status not in ('','active','inactive'):raise ItemError('Select a valid item status.')
    def number(key,default):
        raw=str(args.get(key,default))
        if not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:raise ItemError(f'{key.replace("_"," ").capitalize()} must be a positive integer.')
        return int(raw)
    page=number('page',1);size=number('page_size',25)
    if size not in (25,50,100):raise ItemError('Page size must be 25, 50 or 100.')
    return dict(search=search,category_id=category,status=status,page=page,page_size=size)
