"""Literal text serialization for data-only openpyxl report rows."""
import re

from openpyxl.cell.cell import Cell, ILLEGAL_CHARACTERS_RE


def append_text_row(worksheet, values):
    """Append values without openpyxl interpreting text as formulas or errors.

    Call only for data/label rows, not application-generated formula cells.
    Explicit string typing covers every prefix, including whitespace/controls,
    without changing ordinary identifiers. XML-invalid characters are displayed
    as escape sequences, following the existing Finance/IT export convention.
    Numeric, date and null values retain their native types.
    """
    row = []
    for value in values:
        if isinstance(value, str):
            value = ILLEGAL_CHARACTERS_RE.sub(lambda m: f'\\x{ord(m[0]):02x}', value)
            value = re.sub('[\ud800-\udfff\ufffe\uffff]',
                           lambda m: f'\\u{ord(m[0]):04x}', value)
            cell = Cell(worksheet, value=value)
            cell.data_type = 's'
            row.append(cell)
        else:
            row.append(value)
    worksheet.append(row)
