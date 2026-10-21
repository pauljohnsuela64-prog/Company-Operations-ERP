"""Supplier management inputs and listing; no Procurement/Finance policy changes."""
import re

FIELDS=('supplier_code','supplier_name','contact_person','email','phone','address')


class SupplierError(ValueError):
    def __init__(self,message,status_code=400):
        super().__init__(message)
        self.status_code=status_code


def identifier(value):
    raw=str(value).strip()
    if isinstance(value,bool) or not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:
        raise SupplierError('Select a valid supplier.')
    return int(raw)


def validate_text(value,label,multiline=False):
    if value is None:return
    if not isinstance(value,str):raise SupplierError(f'{label} must be text.')
    if any((ord(c)<32 and not (multiline and c in '\t\r\n')) or ord(c)==127 for c in value):
        raise SupplierError(f'{label} contains unsupported control characters.')
    try:value.encode('utf-8')
    except UnicodeError:raise SupplierError(f'{label} must be valid Unicode.') from None


def submitted_values(form):
    if any(len(form.getlist(name))>1 for name in FIELDS):raise SupplierError('Submit only one value for each supplier field.')
    return [form.get(name,'') for name in FIELDS]


def filters(args):
    keys=('search','status','page','page_size')
    if any(key not in keys for key in args):raise SupplierError('Unsupported supplier filter.')
    if hasattr(args,'getlist') and any(len(args.getlist(key))>1 for key in keys):raise SupplierError('Submit only one value for each supplier filter.')
    search=args.get('search','');validate_text(search,'Search')
    if not isinstance(search,str):raise SupplierError('Search must be text.')
    search=search.strip()
    if len(search)>100:raise SupplierError('Search cannot exceed 100 characters.')
    status=args.get('status','')
    if status not in ('','active','inactive'):raise SupplierError('Select a valid supplier status.')
    def number(key,default):
        raw=str(args.get(key,default))
        if not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:raise SupplierError(f'{key.replace("_"," ").capitalize()} must be a positive integer.')
        return int(raw)
    page=number('page',1);size=number('page_size',25)
    if size not in (25,50,100):raise SupplierError('Page size must be 25, 50 or 100.')
    return dict(search=search,status=status,page=page,page_size=size)


def fields(supplier_code,supplier_name,contact_person=None,email=None,phone=None,address=None):
    from procurement_validation import validate_supplier
    values=[supplier_code,supplier_name,contact_person,email,phone,address]
    result=[]
    for name,value in zip(FIELDS,values):
        validate_text(value,name.replace('_',' ').capitalize(),multiline=name=='address')
        value='' if value is None else value.strip()
        if name=='supplier_code':value=value.upper()
        result.append(value if name in ('supplier_code','supplier_name') else value or None)
    validate_supplier(*result)
    return tuple(result)
