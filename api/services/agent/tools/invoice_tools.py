from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _render_pdf_text(lines: list[str], output_path: Path) -> None:
    # Minimal single-page PDF writer with text-only content.
    escaped = "\n".join(line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines)
    text_commands = ["BT", "/F1 11 Tf", "40 790 Td", "13 TL"]
    for idx, line in enumerate(escaped.split("\n")):
        if idx > 0:
            text_commands.append("T*")
        text_commands.append(f"({line}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("utf-8")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    offsets: list[int] = []
    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_start}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    output_path.write_bytes(bytes(pdf))


@dataclass
class InvoiceLine:
    description: str
    quantity: Decimal
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class InvoiceCreateTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="invoice.create",
        action_class="draft",
        risk_level="medium",
        required_permissions=["invoice.write"],
        execution_policy="auto_execute",
        description="Create invoice payload and generate PDF output.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        customer = str(params.get("customer") or "Customer").strip()
        invoice_number = str(params.get("invoice_number") or f"INV-{context.run_id[-6:]}").strip()
        currency = str(params.get("currency") or "USD").strip().upper()
        due_date = str(params.get("due_date") or "").strip() or "Due on receipt"
        tax_rate = _money(params.get("tax_rate", 0))

        line_payload = params.get("line_items")
        if not isinstance(line_payload, list) or not line_payload:
            line_payload = [
                {"description": "Consulting services", "quantity": 1, "unit_price": 0},
            ]

        lines: list[InvoiceLine] = []
        for row in line_payload:
            if not isinstance(row, dict):
                continue
            lines.append(
                InvoiceLine(
                    description=str(row.get("description") or "Line item"),
                    quantity=_money(row.get("quantity", 1)),
                    unit_price=_money(row.get("unit_price", 0)),
                )
            )

        if not lines:
            raise ToolExecutionError("Invoice requires at least one valid line item.")

        subtotal = sum((line.total for line in lines), start=Decimal("0.00"))
        tax_amount = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = subtotal + tax_amount

        out_dir = Path(".maia_agent") / "invoices"
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"{invoice_number}.pdf"
        text_lines = [
            f"Invoice: {invoice_number}",
            f"Customer: {customer}",
            f"Due date: {due_date}",
            "",
            "Line items:",
        ]
        for line in lines:
            text_lines.append(
                f"- {line.description} | qty {line.quantity} | unit {line.unit_price} | total {line.total} {currency}"
            )
        text_lines.extend(
            [
                "",
                f"Subtotal: {subtotal} {currency}",
                f"Tax ({tax_rate}%): {tax_amount} {currency}",
                f"Total: {total} {currency}",
            ]
        )
        _render_pdf_text(text_lines, pdf_path)

        content = (
            f"Created invoice `{invoice_number}` for {customer}.\n"
            f"- Subtotal: {subtotal} {currency}\n"
            f"- Tax: {tax_amount} {currency}\n"
            f"- Total: {total} {currency}\n"
            f"- PDF: {pdf_path.as_posix()}"
        )
        return ToolExecutionResult(
            summary=f"Invoice {invoice_number} generated.",
            content=content,
            data={
                "invoice_number": invoice_number,
                "customer": customer,
                "currency": currency,
                "subtotal": str(subtotal),
                "tax_amount": str(tax_amount),
                "total": str(total),
                "pdf_path": str(pdf_path.resolve()),
            },
            sources=[],
            next_steps=["Review invoice and send to customer."],
            events=[
                ToolTraceEvent(
                    event_type="doc_open",
                    title="Open invoice template",
                    detail=f"Preparing invoice {invoice_number}",
                    data={"invoice_number": invoice_number},
                ),
                ToolTraceEvent(
                    event_type="doc_insert_text",
                    title="Populate invoice fields",
                    detail=f"Filled customer, totals, and due date for {customer}",
                    data={"customer": customer, "total": str(total), "currency": currency},
                ),
                ToolTraceEvent(
                    event_type="doc_save",
                    title="Save invoice document",
                    detail=f"Saved invoice PDF to {pdf_path.as_posix()}",
                    data={"pdf_path": str(pdf_path.resolve())},
                ),
            ],
        )


class InvoiceSendTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="invoice.send",
        action_class="execute",
        risk_level="high",
        required_permissions=["invoice.send"],
        execution_policy="confirm_before_execute",
        description="Send invoice through accounting connector and optional email.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        invoice_number = str(params.get("invoice_number") or "").strip()
        if not invoice_number:
            match = re.search(r"\bINV[-_ ]?[A-Za-z0-9]+\b", prompt, flags=re.IGNORECASE)
            if match:
                invoice_number = match.group(0).replace(" ", "")
        if not invoice_number:
            raise ToolExecutionError("invoice_number is required to send invoice.")

        connector = get_connector_registry().build("invoice", settings=context.settings)
        payload = dict(params)
        payload.setdefault("invoice_number", invoice_number)
        response = connector.post_invoice(payload)
        content = (
            f"Invoice `{invoice_number}` queued in {response.get('provider')} with status "
            f"`{response.get('status')}`."
        )
        return ToolExecutionResult(
            summary=f"Invoice {invoice_number} send flow executed.",
            content=content,
            data=response,
            sources=[],
            next_steps=["Monitor payment status and send reminder if overdue."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Submit invoice to connector",
                    detail=f"Dispatching invoice {invoice_number}",
                    data={"invoice_number": invoice_number},
                )
            ],
        )
