"""Optimistic concurrency contract for HR master records."""
from dataclasses import dataclass
import re

from hr_validation import HRValidationError, form_values

MAX_REVISION = 9223372036854775807


class HRRevisionInputError(HRValidationError):
    pass


class HRConflictError(Exception):
    pass


class HRMissingRecordError(Exception):
    pass


class HRRevisionExhaustedError(Exception):
    pass


@dataclass(frozen=True)
class HRWriteResult:
    revision: int
    changed: bool = True


def revision(value):
    raw = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,19}', raw) or not 1 <= int(raw) <= MAX_REVISION:
        raise HRRevisionInputError('The form version is missing or invalid. Reload the form and try again.')
    return int(raw)


def form_revision(form):
    try:
        value = form_values(form, ('expected_revision',))['expected_revision']
    except HRValidationError:
        raise HRRevisionInputError('Submit only one form version. Reload the form and try again.') from None
    return revision(value)


def require_current(current, expected):
    if current != expected:
        raise HRConflictError('This record changed since you opened the form. Your changes were not saved.')


def require_incrementable(current):
    if current >= MAX_REVISION:
        raise HRRevisionExhaustedError('This record cannot be saved right now. Contact an administrator.')
