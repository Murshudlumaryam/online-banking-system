"""
PDF account statement generation (Phase 7).

Uses reportlab's Platypus layer (SimpleDocTemplate + Table) rather than the
raw canvas API, since a statement is fundamentally a titled document with a
data table — Platypus handles pagination automatically if the ledger has
enough entries to span multiple pages.
"""
import io
from datetime import date, datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.accounts.models import Account
from app.modules.customers.models import Customer
from app.modules.ledger_entries.models import LedgerEntry, LedgerEntryType

_HEADER_COLOR = colors.HexColor("#123C4D")
_ROW_ALT_COLOR = colors.HexColor("#F5F6F7")
_GRID_COLOR = colors.HexColor("#D3D7DB")


def generate_account_statement_pdf(
    *,
    account: Account,
    customer: Customer,
    entries: list[LedgerEntry],
    start_date: date,
    end_date: date,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Statement {account.account_number}",
        topMargin=54,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Online Banking System", styles["Title"]))
    story.append(Paragraph("Account Statement", styles["Heading2"]))
    story.append(Spacer(1, 10))

    for line in (
        f"Account holder: {customer.first_name} {customer.last_name}",
        f"Account number: {account.account_number}",
        f"Account type: {account.account_type} | Currency: {account.currency}",
        f"Statement period: {start_date.isoformat()} to {end_date.isoformat()}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    ):
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 16))

    table_data = [["Date", "Type", "Amount", "Balance after"]]
    for entry in entries:
        sign = "-" if entry.entry_type == LedgerEntryType.DEBIT else "+"
        table_data.append(
            [
                entry.created_at.strftime("%Y-%m-%d %H:%M"),
                entry.entry_type.value,
                f"{sign}{entry.amount:.2f} {entry.currency}",
                f"{entry.balance_after:.2f} {entry.currency}",
            ]
        )

    table = Table(table_data, colWidths=[100, 70, 140, 140], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID_COLOR),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT_COLOR]),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    if not entries:
        story.append(Spacer(1, 12))
        story.append(Paragraph("No transactions in this period.", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
