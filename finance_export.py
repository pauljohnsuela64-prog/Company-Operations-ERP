# ==========================================================
# FINANCE - EXCEL EXPORT
# ==========================================================

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter


# ==========================================================
# AUTO SIZE COLUMNS
# ==========================================================

def auto_size_columns(worksheet):

    for column_cells in worksheet.columns:

        max_length = 0

        column_letter = get_column_letter(
            column_cells[0].column
        )

        for cell in column_cells:

            if cell.value is not None:

                cell_length = len(
                    str(cell.value)
                )

                if cell_length > max_length:
                    max_length = cell_length

        worksheet.column_dimensions[
            column_letter
        ].width = max_length + 2


# ==========================================================
# GENERATE FINANCE REPORT
# ==========================================================

def generate_finance_report_excel(
    year,
    summary,
    monthly_expenses,
    category_expenses,
    expense_records,
):

    workbook = Workbook()


    # ======================================================
    # SUMMARY SHEET
    # ======================================================

    summary_sheet = workbook.active
    summary_sheet.title = "Summary"

    summary_sheet.append(
        [
            "Finance Report",
            year,
        ]
    )

    summary_sheet.append([])

    summary_sheet.append(
        [
            "Status",
            "Records",
            "Amount",
        ]
    )

    summary_sheet.append(
        [
            "Total",
            summary["total_expenses"],
            summary["total_amount"],
        ]
    )

    summary_sheet.append(
        [
            "Draft",
            summary["draft_count"],
            summary["draft_amount"],
        ]
    )

    summary_sheet.append(
        [
            "Approved",
            summary["approved_count"],
            summary["approved_amount"],
        ]
    )

    summary_sheet.append(
        [
            "Paid",
            summary["paid_count"],
            summary["paid_amount"],
        ]
    )

    summary_sheet.append(
        [
            "Cancelled",
            summary["cancelled_count"],
            summary["cancelled_amount"],
        ]
    )


    # ======================================================
    # MONTHLY PAID EXPENSES
    # ======================================================

    monthly_sheet = workbook.create_sheet(
        "Monthly Paid Expenses"
    )

    monthly_sheet.append(
        [
            "Month",
            "Paid Expenses",
            "Total Amount",
        ]
    )

    for month in monthly_expenses:

        monthly_sheet.append(
            [
                month["month_name"],
                month["expense_count"],
                month["total_amount"],
            ]
        )


    # ======================================================
    # CATEGORY BREAKDOWN
    # ======================================================

    category_sheet = workbook.create_sheet(
        "Category Breakdown"
    )

    category_sheet.append(
        [
            "Category Code",
            "Category",
            "Paid Expenses",
            "Total Amount",
        ]
    )

    for category in category_expenses:

        category_sheet.append(
            [
                category["category_code"],
                category["category_name"],
                category["expense_count"],
                category["total_amount"],
            ]
        )


    # ======================================================
    # EXPENSE RECORDS
    # ======================================================

    expense_sheet = workbook.create_sheet(
        "Expense Records"
    )

    expense_sheet.append(
        [
            "Expense Number",
            "Date",
            "Category",
            "Department",
            "Supplier",
            "Purchase Order",
            "Description",
            "Amount",
            "Status",
            "Reference Number",
            "Payment Method",
        ]
    )

    for expense in expense_records:

        expense_sheet.append(
            [
                expense["expense_number"],
                expense["expense_date"],
                expense["category_name"],
                expense["department_name"] or "",
                expense["supplier_name"] or "",
                expense["po_number"] or "",
                expense["description"],
                expense["amount"],
                expense["status"],
                expense["reference_number"] or "",
                expense["payment_method"] or "",
            ]
        )


    # ======================================================
    # FORMATTING
    # ======================================================

    for worksheet in workbook.worksheets:

        for cell in worksheet[1]:

            cell.font = Font(
                bold=True
            )

            cell.alignment = Alignment(
                vertical="center"
            )

        auto_size_columns(
            worksheet
        )


    # ======================================================
    # CURRENCY FORMAT
    # ======================================================

    for row in range(
        4,
        summary_sheet.max_row + 1,
    ):
        summary_sheet.cell(
            row=row,
            column=3,
        ).number_format = '₱#,##0.00'


    for row in range(
        2,
        monthly_sheet.max_row + 1,
    ):
        monthly_sheet.cell(
            row=row,
            column=3,
        ).number_format = '₱#,##0.00'


    for row in range(
        2,
        category_sheet.max_row + 1,
    ):
        category_sheet.cell(
            row=row,
            column=4,
        ).number_format = '₱#,##0.00'


    for row in range(
        2,
        expense_sheet.max_row + 1,
    ):
        expense_sheet.cell(
            row=row,
            column=8,
        ).number_format = '₱#,##0.00'


    # ======================================================
    # CREATE FILE IN MEMORY
    # ======================================================

    output = BytesIO()

    workbook.save(
        output
    )

    output.seek(0)

    return output