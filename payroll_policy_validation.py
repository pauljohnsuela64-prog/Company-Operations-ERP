"""Bounded application contract matching the immutable migration 005 definitions."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import hmac
import json
import re

def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties),
                additionalProperties=False, maxProperties=len(properties))


def choices(*values):
    return {'enum': list(values)}


# These are bounded vocabularies, not executable formulas or company approvals.
# UNRESOLVED is permitted in drafts only. BLOCK is an explicit supported restriction.
JSON_RULES = {
    'cutoff_rules': object_schema(dict(a_start=choices(1), a_end=choices(15),
                                      b_start=choices(16), b_end=choices('MONTH_END'))),
    'supported_pay_types': dict(type='array', items=choices('MONTHLY'), minItems=1,
                                maxItems=1, uniqueItems=True),
    'attendance_rules': object_schema(dict(
        missing_evidence=choices('BLOCK'),
        late_treatment=choices('UNRESOLVED', 'NO_DEDUCTION', 'BLOCK'),
        absence_treatment=choices('UNRESOLVED', 'PERIOD_WORKDAY_DIVISOR', 'BLOCK'),
        half_day_treatment=choices('UNRESOLVED', 'HALF_DAY_DEDUCTION', 'BLOCK'))),
    'leave_rules': object_schema(dict(
        paid_leave_treatment=choices('UNRESOLVED', 'NO_DEDUCTION', 'BLOCK'),
        unpaid_leave_treatment=choices('UNRESOLVED', 'PERIOD_WORKDAY_DIVISOR', 'BLOCK'),
        conflict=choices('BLOCK'))),
    'eligibility_rules': object_schema(dict(proration=choices('BLOCK'),
        full_cutoff_eligibility=choices('UNRESOLVED', 'VERIFIED_FULL_CUTOFF_ONLY'))),
    'deduction_rules': object_schema(dict(
        excess_deductions=choices('UNRESOLVED', 'ZERO_FLOOR', 'BLOCK'),
        statutory=choices('UNRESOLVED', 'EXTERNAL_APPROVED_PROCESS', 'BLOCK'),
        odd_cent_handling=choices('UNRESOLVED', 'ROUND_EACH_CUTOFF', 'BLOCK'))),
    'payment_rules': object_schema(dict(mode=choices('MANUAL'))),
}

FIXED = dict(calculator_key='MONTHLY_SEMIMONTHLY_V1', calendar_key='SEMI_MONTHLY_1_15_16_EOM_V1',
             frequency='SEMI_MONTHLY', working_week_mask=31, currency_code='PHP',
             full_cutoff_divisor=2, rounding_mode='ROUND_HALF_UP', rounding_scale=2)
CONFIG_FIELDS = ('policy_name', 'effective_from', *FIXED, *JSON_RULES)
PERMISSIONS = ('payroll.policy.manage', 'payroll.policy.approve', 'payroll.policy.activate')


def initial_policy():
    rules = {}
    for name, schema in JSON_RULES.items():
        if schema['type'] == 'array':
            rules[name] = ['MONTHLY']
        else:
            rules[name] = {key: prop['enum'][0] for key, prop in schema['properties'].items()}
    return dict(policy_name='', effective_from='', **FIXED, **rules)


def text(value, label, maximum, required=True):
    if not isinstance(value, str):
        raise ValueError(f'{label} must be text.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{label} is required.')
    if len(value) > maximum:
        raise ValueError(f'{label} must not exceed {maximum} characters.')
    return value


def positive_integer(value, label, maximum=4294967295):
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,10}', str(value)):
        raise ValueError(f'{label} must be a valid positive integer.')
    result = int(value)
    if not 1 <= result <= maximum:
        raise ValueError(f'{label} is outside the supported range.')
    return result


def effective_date(value):
    if isinstance(value, datetime):
        raise ValueError('Effective date must not include a time.')
    if not isinstance(value, date):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('Effective date must be a valid YYYY-MM-DD date.')
        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise ValueError('Effective date must be a valid calendar date.') from None
    if value.year < 1000 or value.day not in (1, 16):
        raise ValueError('Effective date must be the 1st or 16th, within MySQL years 1000–9999.')
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Configuration JSON must not contain duplicate keys.')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Configuration JSON must not contain nonfinite numbers.')


def rule_value(name, value):
    if isinstance(value, str):
        if len(value) > 4096:
            raise ValueError(f'{name.replace("_", " ").capitalize()} configuration is too long.')
        try:
            value = json.loads(value, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        except (ValueError, RecursionError):
            raise ValueError(f'{name.replace("_", " ").capitalize()} must contain valid bounded JSON without duplicate keys.') from None
    schema = JSON_RULES[name]
    if schema['type'] == 'array':
        if value != ['MONTHLY']:
            raise ValueError('Supported pay types must be exactly MONTHLY.')
        return list(value)
    if not isinstance(value, dict) or set(value) != set(schema['properties']):
        raise ValueError(f'{name.replace("_", " ").capitalize()} has missing or unsupported configuration keys.')
    for key, item in value.items():
        if not any(type(item) is type(option) and item == option for option in schema['properties'][key]['enum']):
            raise ValueError(f'{name.replace("_", " ").capitalize()}: unsupported value for {key.replace("_", " ")}.')
    return dict(value)


def policy_values(payload):
    if not isinstance(payload, dict) or set(payload) != set(CONFIG_FIELDS):
        raise ValueError('Policy submission has missing or unsupported fields.')
    result = dict(policy_name=text(payload['policy_name'], 'Policy name', 100),
                  effective_from=effective_date(payload['effective_from']))
    for name, expected in FIXED.items():
        value = payload[name]
        if type(expected) is int:
            value = positive_integer(value, name.replace('_', ' ').capitalize())
        if type(value) is not type(expected) or value != expected:
            raise ValueError(f'Unsupported {name.replace("_", " ")}. Only the initial development template is supported.')
        result[name] = value
    result.update({name: rule_value(name, payload[name]) for name in JSON_RULES})
    return result


def require_resolved(values):
    for name in JSON_RULES:
        value = values[name]
        if isinstance(value, dict) and 'UNRESOLVED' in value.values():
            raise ValueError('Required policy rules remain UNRESOLVED. Obtain the relevant business approvals before approving.')


def approval_reference(value):
    value = text(value, 'Approval reference', 255)
    if (len(value) < 3 or not any(c.isalnum() for c in value)
            or value.casefold() in {'pending', 'unresolved', 'n/a', 'none', 'tbd', 'todo'}):
        raise ValueError('Provide a meaningful reference to the required business approvals; placeholders are not accepted.')
    return value


def configuration_hash(policy):
    values = policy_values({name: policy[name] for name in CONFIG_FIELDS})
    values['effective_from'] = values['effective_from'].isoformat()
    payload = dict(hash_version=1, policy_version_id=policy['policy_version_id'],
                   version_number=policy['version_number'], configuration=values,
                   approval_reference=approval_reference(policy['approval_reference']))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def verify_configuration_hash(policy):
    digest = policy.get('configuration_hash')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or not hmac.compare_digest(digest, configuration_hash(policy)):
        raise ValueError('Approved policy configuration hash does not match. Activation was not scheduled.')


def company_today(timezone_name):
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError('Payroll company timezone is not configured. Activation is blocked until ERP_PAYROLL_TIMEZONE is set.')
    try:
        zone = ZoneInfo(timezone_name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Payroll company timezone is invalid or timezone data is unavailable. Activation is blocked.') from None
    return datetime.now(timezone.utc).astimezone(zone).date()


def form_values(values):
    """Flatten configuration into ordinary controls; never discard a submitted value."""
    result = {}
    for name in ('policy_name', 'effective_from', *FIXED):
        value = values.get(name, '')
        result[name] = value.isoformat() if isinstance(value, date) else str(value)
    for name, schema in JSON_RULES.items():
        value = values.get(name)
        if schema['type'] == 'array' or name in ('cutoff_rules', 'payment_rules'):
            result[name] = json.dumps(value, separators=(',', ':'))
        else:
            for key in schema['properties']:
                result[name+'.'+key] = value.get(key, '') if isinstance(value, dict) else ''
    return result


def parse_form(form, editing=False):
    allowed = set(form_values(initial_policy())) | {'csrf_token'}
    if editing:
        allowed.add('revision')
    if set(form) - allowed or any(len(form.getlist(key)) != 1 for key in form):
        raise ValueError('Policy submission has unsupported or repeated fields.')
    payload = {name: form.get(name, '') for name in ('policy_name', 'effective_from', *FIXED)}
    for name, schema in JSON_RULES.items():
        if name in form_values(initial_policy()):
            payload[name] = form.get(name, '')
        else:
            payload[name] = {key: form.get(name+'.'+key, '') for key in schema['properties']}
    return policy_values(payload)

