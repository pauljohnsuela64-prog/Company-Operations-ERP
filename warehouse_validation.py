"""Warehouse-only validation; no inventory or leave policies."""
import re


class WarehouseError(ValueError):
    def __init__(self,message,status_code=400):
        super().__init__(message)
        self.status_code=status_code


def identifier(value):
    raw=str(value)
    if isinstance(value,bool) or not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:
        raise WarehouseError('Select a valid warehouse.')
    return int(raw)


def fields(code,name,location):
    result=[]
    for value,label,limit,required,upper in ((code,'Warehouse code',30,True,True),(name,'Warehouse name',100,True,False),(location,'Warehouse location',255,False,False)):
        if value is None:value=''
        if not isinstance(value,str):raise WarehouseError(f'{label} must be text.')
        if any(ord(c)<32 or ord(c)==127 for c in value):raise WarehouseError(f'{label} contains unsupported control characters.')
        try:value.encode('utf-8')
        except UnicodeError:raise WarehouseError(f'{label} must be valid Unicode.') from None
        value=value.strip()
        if upper:value=value.upper()
        if required and not value:raise WarehouseError(f'{label} is required.')
        if len(value)>limit:raise WarehouseError(f'{label} cannot exceed {limit} characters.')
        result.append(value if required else value or None)
    return tuple(result)


def filters(args):
    keys=('search','status','page','page_size')
    if any(key not in keys for key in args):raise WarehouseError('Unsupported warehouse filter.')
    if hasattr(args,'getlist') and any(len(args.getlist(key))>1 for key in keys):raise WarehouseError('Submit only one value for each warehouse filter.')
    search=args.get('search','')
    if not isinstance(search,str) or any(ord(c)<32 or ord(c)==127 for c in search):raise WarehouseError('Search must be text without control characters.')
    try:search.encode('utf-8')
    except UnicodeError:raise WarehouseError('Search must be valid Unicode.') from None
    search=search.strip()
    if len(search)>100:raise WarehouseError('Search cannot exceed 100 characters.')
    status=args.get('status','')
    if status not in ('','active','inactive'):raise WarehouseError('Select a valid warehouse status.')
    def number(key,default):
        raw=str(args.get(key,default))
        if not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:raise WarehouseError(f'{key.replace("_"," ").capitalize()} must be a positive integer.')
        return int(raw)
    page=number('page','1');size=number('page_size','25')
    if size not in (25,50,100):raise WarehouseError('Page size must be 25, 50 or 100.')
    return dict(search=search,status=status,page=page,page_size=size)
