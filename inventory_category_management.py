"""Inventory Category inputs and listing; item assignments remain unchanged."""
import re

FIELDS=('category_code','category_name','description')


class CategoryError(ValueError):
    def __init__(self,message,status_code=400):
        super().__init__(message)
        self.status_code=status_code


def identifier(value):
    raw=str(value).strip()
    if isinstance(value,bool) or not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:
        raise CategoryError('Select a valid inventory category.')
    return int(raw)


def validate_text(value,label,multiline=False):
    if value is None:return
    if not isinstance(value,str):raise CategoryError(f'{label} must be text.')
    if any((ord(c)<32 and not (multiline and c in '\t\r\n')) or ord(c)==127 for c in value):
        raise CategoryError(f'{label} contains unsupported control characters.')
    try:value.encode('utf-8')
    except UnicodeError:raise CategoryError(f'{label} must be valid Unicode.') from None


def submitted_values(form):
    if any(len(form.getlist(name))>1 for name in FIELDS):raise CategoryError('Submit only one value for each category field.')
    return [form.get(name,'') for name in FIELDS]


def filters(args):
    keys=('search','status','page','page_size')
    if any(key not in keys for key in args):raise CategoryError('Unsupported category filter.')
    if hasattr(args,'getlist') and any(len(args.getlist(key))>1 for key in keys):raise CategoryError('Submit only one value for each category filter.')
    search=args.get('search','');validate_text(search,'Search')
    if not isinstance(search,str):raise CategoryError('Search must be text.')
    search=search.strip()
    if len(search)>100:raise CategoryError('Search cannot exceed 100 characters.')
    status=args.get('status','')
    if status not in ('','active','inactive'):raise CategoryError('Select a valid category status.')
    def number(key,default):
        raw=str(args.get(key,default))
        if not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:raise CategoryError(f'{key.replace("_"," ").capitalize()} must be a positive integer.')
        return int(raw)
    page=number('page',1);size=number('page_size',25)
    if size not in (25,50,100):raise CategoryError('Page size must be 25, 50 or 100.')
    return dict(search=search,status=status,page=page,page_size=size)
