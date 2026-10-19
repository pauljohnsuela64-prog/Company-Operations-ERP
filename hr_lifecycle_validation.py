"""Pure synthetic structure validation; neither source verification nor HR policy."""
from datetime import date
import json
import math
import re

EVENT_TYPES = frozenset(('HIRE', 'STATUS_CHANGE', 'RESIGN', 'TERMINATE', 'REHIRE',
                        'TRANSFER', 'POSITION_CHANGE', 'CORRECT', 'VOID', 'LEGACY_OBSERVATION'))
INT_MAX = 2147483647
BIGINT_MAX = 9223372036854775807


class LifecycleInputError(ValueError):
    """Safe structural error; never includes submitted content."""


def positive_integer(value, label, maximum=BIGINT_MAX):
    if type(value) is not int or not 1 <= value <= maximum:
        raise LifecycleInputError(f'{label} must be a bounded positive integer.')
    return value


def business_date(value, label):
    if type(value) is not date or value.year < 1000:
        raise LifecycleInputError(f'{label} must be a DATE within 1000-9999, without a time.')
    return value


def bounded_text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise LifecycleInputError(f'{label} must be nonblank text within its field limit.')
    # Reject strings that cannot be encoded as UTF-8 (including lone surrogates).
    try:value.encode('utf-8')
    except UnicodeError:raise LifecycleInputError(f'{label} must be valid Unicode.') from None
    return value  # No silent normalization of evidence.


def json_object(value):
    """Bound JSON-compatible objects without coercing dates/Decimal or NaN."""
    def inspect(node, depth=0):
        if depth > 32:raise LifecycleInputError('JSON nesting exceeds the structural limit.')
        if type(node) is dict:
            for key,item in node.items():
                if type(key) is not str:raise LifecycleInputError('JSON object keys must be text.')
                inspect(key,depth+1);inspect(item,depth+1)
        elif type(node) is list:
            for item in node:inspect(item,depth+1)
        elif node is None or type(node) in (str,bool):pass
        elif type(node) is int:
            if not -BIGINT_MAX-1 <= node <= BIGINT_MAX:raise LifecycleInputError('JSON integer is outside the supported range.')
        elif type(node) is float:
            if not math.isfinite(node):raise LifecycleInputError('JSON numbers must be finite.')
        else:raise LifecycleInputError('Unsupported JSON value type.')
    if type(value) is not dict:raise LifecycleInputError('Payload must be a JSON object.')
    inspect(value)
    try:
        # Conservative size check includes spaces; MySQL may format JSON similarly.
        encoded=json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True)
        if len(encoded.encode('utf-8')) > 16384:raise LifecycleInputError('Payload exceeds 16384 bytes.')
        return json.loads(encoded)  # Detached value; no mutation or shared references.
    except (UnicodeError,ValueError,RecursionError):
        raise LifecycleInputError('Payload is invalid or exceeds its structural limit.') from None


def validate_proposal(proposal):
    """Synthetic v1 envelope. Omitted fields are unchanged; clear is explicit.

    Does not check record existence, transition eligibility, source authenticity,
    approval separation, period overlap, or permission to publish.
    """
    required={'schema_version','employee_id','expected_employee_revision','event_type',
              'effective_date','effective_order','source','reason','submitted_by','changes'}
    optional={'employment_period_id','supersedes_event_id'}
    if type(proposal) is not dict or not required <= proposal.keys() or proposal.keys()-required-optional:
        raise LifecycleInputError('Proposal has missing or unsupported fields.')
    if type(proposal['schema_version']) is not int or proposal['schema_version'] != 1:
        raise LifecycleInputError('Only structural schema version 1 is supported.')
    for field,limit in [('employee_id',INT_MAX),('submitted_by',INT_MAX),
                        ('expected_employee_revision',BIGINT_MAX),('effective_order',INT_MAX)]:
        positive_integer(proposal[field],field,limit)
    business_date(proposal['effective_date'],'effective_date')
    if type(proposal['event_type']) is not str or proposal['event_type'] not in EVENT_TYPES:
        raise LifecycleInputError('Unsupported event type.')
    for field in optional:
        if field in proposal and proposal[field] is not None:positive_integer(proposal[field],field)
    correcting=proposal['event_type'] in ('CORRECT','VOID')
    if correcting != (proposal.get('supersedes_event_id') is not None):
        raise LifecycleInputError('Correction reference does not match the event structure.')
    source=proposal['source']
    if type(source) is not dict or not {'type','reference'} <= source.keys() or source.keys()-{'type','reference','version'}:
        raise LifecycleInputError('Source requires type/reference and optional version.')
    for key,limit in [('type',30),('reference',255),('version',50)]:
        if key!='version' or source.get(key) is not None:bounded_text(source[key],'source '+key,limit)
    bounded_text(proposal['reason'],'reason',255)
    changes=proposal['changes']
    if type(changes) is not dict:raise LifecycleInputError('Changes must be an object.')
    # Technical fields only. No type-specific employment-transition rule is inferred.
    fields={'employment_status':30,'job_title':100,'department_id':INT_MAX,
            'verified_start_date':None,'end_exclusive_date':None}
    encoded_changes={}
    for field,change in changes.items():
        if field not in fields or type(change) is not dict:
            raise LifecycleInputError('Unsupported change field or structure.')
        if change == {'op':'clear'}:
            encoded_changes[field]={'op':'clear'}
        elif set(change)=={'op','value'} and change['op']=='set' and change['value'] is not None:
            value=change['value']
            if field=='department_id':positive_integer(value,field,INT_MAX)
            elif field.endswith('_date'):value=business_date(value,field).isoformat()
            else:bounded_text(value,field,fields[field])
            encoded_changes[field]={'op':'set','value':value}
        else:raise LifecycleInputError('Use explicit set/value or clear; omit unchanged fields.')
    result=dict(proposal)
    result['source']=dict(source)
    result['changes']=json_object(encoded_changes)
    return result
