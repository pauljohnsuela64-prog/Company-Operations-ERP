"""Bounded Audit Logs read filters; never modify audit events."""
from datetime import date
import re

FIELDS=('search','module','action','start_date','end_date','page','page_size')


class AuditLogError(ValueError):
    def __init__(self,message,status_code=400):
        super().__init__(message)
        self.status_code=status_code


def text(value,label,maximum):
    if not isinstance(value,str):
        raise AuditLogError(f'{label} must be text.')
    if any(ord(c)<32 or ord(c)==127 for c in value):
        raise AuditLogError(f'{label} contains unsupported control characters.')
    value=value.strip()
    if len(value)>maximum:
        raise AuditLogError(f'{label} must not exceed {maximum} characters.')
    try:value.encode('utf-8')
    except UnicodeError:raise AuditLogError(f'{label} must be valid Unicode.') from None
    return value


def calendar_date(value):
    if value is None or value=='':return None
    try:
        if type(value) is date:result=value
        elif isinstance(value,str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value.strip()):result=date.fromisoformat(value.strip())
        else:raise ValueError
        if result.year<1000:raise ValueError
        return result
    except ValueError:
        raise AuditLogError('Audit dates must be valid YYYY-MM-DD dates between years 1000 and 9999.') from None


def positive(value,label):
    raw=str(value).strip()
    if isinstance(value,bool) or not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=2147483647:
        raise AuditLogError(f'{label} must be a valid positive integer.')
    return int(raw)


def filter_values(args):
    if any(field not in FIELDS for field in args):
        raise AuditLogError('Unsupported Audit Logs filter.')
    if hasattr(args,'getlist') and any(len(args.getlist(field))>1 for field in FIELDS):
        raise AuditLogError('Submit only one value for each Audit Logs filter.')
    start=calendar_date(args.get('start_date',''))
    end=calendar_date(args.get('end_date',''))
    if start and end and start>end:
        raise AuditLogError('Audit log start date cannot be later than end date.')
    size=positive(args.get('page_size','25'),'Page size')
    if size not in (25,50,100):raise AuditLogError('Page size must be 25, 50 or 100.')
    return dict(search=text(args.get('search',''),'Search',100),module=text(args.get('module',''),'Module',50),
        action=text(args.get('action',''),'Action',50),start_date=start,end_date=end,
        page=positive(args.get('page','1'),'Page'),page_size=size)
