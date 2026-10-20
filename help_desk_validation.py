"""Help Desk storage/input rules; no SLA, eligibility or escalation policy."""
import re

STATUSES = ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')
PRIORITIES = ('LOW', 'MEDIUM', 'HIGH', 'URGENT')
CREATE_FIELDS = ('employee_id', 'category_id', 'subject', 'description', 'priority')


class HelpDeskError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def identifier(value, label='Ticket'):
    raw = str(value).strip()
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,10}', raw) or not 1 <= int(raw) <= 2147483647:
        raise HelpDeskError(f'{label} must be a valid positive ID.')
    return int(raw)


def text(value, label, maximum, required=False, byte_limit=None):
    if not isinstance(value, str):
        raise HelpDeskError(f'{label} must be text.')
    value = value.strip()
    if required and not value:
        raise HelpDeskError(f'{label} is required.')
    if len(value) > maximum:
        raise HelpDeskError(f'{label} must not exceed {maximum} characters.')
    try:
        encoded = value.encode('utf-8')
    except UnicodeError:
        raise HelpDeskError(f'{label} must be valid Unicode.') from None
    if byte_limit is not None and len(encoded) > byte_limit:
        raise HelpDeskError(f'{label} exceeds the existing TEXT storage limit ({byte_limit} UTF-8 bytes).')
    if any((ord(c) < 32 and c not in '\t\n\r') or ord(c) == 127 for c in value):
        raise HelpDeskError(f'{label} contains unsupported control characters.')
    return value


def unique_values(source, fields):
    if hasattr(source, 'getlist') and any(len(source.getlist(field)) > 1 for field in fields):
        raise HelpDeskError('Submit only one value for each Help Desk field or filter.')
    return {field: source.get(field, 'MEDIUM' if field == 'priority' else '') for field in fields}


def create_values(raw):
    priority = text(raw.get('priority', 'MEDIUM'), 'Priority', 20).upper()
    if priority not in PRIORITIES:
        raise HelpDeskError('Invalid ticket priority.')
    return dict(employee_id=identifier(raw.get('employee_id'), 'Employee'), category_id=identifier(raw.get('category_id'), 'Category'),
                subject=text(raw.get('subject'), 'Subject', 150, True),
                description=text(raw.get('description'), 'Description', 65535, True, 65535), priority=priority)


def resolution_value(value):
    return text(value, 'Resolution', 65535, True, 65535)


def listing_values(args):
    defaults = dict(search='', status='', priority='', category_id='', assigned_to='', page='1', page_size='25')
    unique_values(args, defaults)
    raw = {key: args.get(key, default) for key, default in defaults.items()}
    status = text(raw['status'], 'Status', 20).upper()
    priority = text(raw['priority'], 'Priority', 20).upper()
    if status and status not in STATUSES:
        raise HelpDeskError('Invalid ticket status.')
    if priority and priority not in PRIORITIES:
        raise HelpDeskError('Invalid ticket priority.')
    size = identifier(raw['page_size'], 'Page size')
    if size not in (25, 50, 100):
        raise HelpDeskError('Page size must be 25, 50 or 100.')
    assigned = raw['assigned_to']
    if assigned not in ('', None, 'unassigned'):
        assigned = identifier(assigned, 'Technician')
    return dict(search=text(raw['search'], 'Search', 100), status=status, priority=priority,
                category_id=identifier(raw['category_id'], 'Category') if raw['category_id'] else None,
                assigned_to=assigned or None, page=identifier(raw['page'], 'Page'), page_size=size)
