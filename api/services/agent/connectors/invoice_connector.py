from __future__ import annotations

from typing import Any

from datetime import date

from .base import BaseConnector, ConnectorError, ConnectorHealth


class InvoiceConnector(BaseConnector):
    connector_id = "invoice"

    def _quickbooks_token(self) -> str:
        token = self._read_secret("QUICKBOOKS_ACCESS_TOKEN")
        if not token:
            raise ConnectorError("QUICKBOOKS_ACCESS_TOKEN is not configured.")
        return token

    def _quickbooks_realm_id(self) -> str:
        realm_id = self._read_secret("QUICKBOOKS_REALM_ID")
        if not realm_id:
            raise ConnectorError("QUICKBOOKS_REALM_ID is not configured.")
        return realm_id

    def _xero_token(self) -> str:
        token = self._read_secret("XERO_ACCESS_TOKEN")
        if not token:
            raise ConnectorError("XERO_ACCESS_TOKEN is not configured.")
        return token

    def _xero_tenant_id(self) -> str:
        tenant_id = self._read_secret("XERO_TENANT_ID")
        if not tenant_id:
            raise ConnectorError("XERO_TENANT_ID is not configured.")
        return tenant_id

    def _line_items(self, invoice_payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = invoice_payload.get("line_items") or []
        if not isinstance(rows, list) or not rows:
            rows = [
                {
                    "description": "Service",
                    "quantity": 1,
                    "unit_price": 0,
                }
            ]
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "description": str(row.get("description") or "Line item"),
                    "quantity": float(row.get("quantity") or 1),
                    "unit_price": float(row.get("unit_price") or 0),
                    "item_id": str(row.get("item_id") or "").strip(),
                    "account_code": str(row.get("account_code") or "200").strip(),
                }
            )
        return normalized

    def health_check(self) -> ConnectorHealth:
        quickbooks_token = self._read_secret("QUICKBOOKS_ACCESS_TOKEN")
        quickbooks_realm = self._read_secret("QUICKBOOKS_REALM_ID")
        xero_token = self._read_secret("XERO_ACCESS_TOKEN")
        xero_tenant = self._read_secret("XERO_TENANT_ID")
        if not quickbooks_token and not xero_token:
            return ConnectorHealth(
                self.connector_id,
                False,
                "Configure QUICKBOOKS_ACCESS_TOKEN or XERO_ACCESS_TOKEN.",
            )
        if quickbooks_token and quickbooks_realm:
            return ConnectorHealth(self.connector_id, True, "quickbooks configured")
        if xero_token and xero_tenant:
            return ConnectorHealth(self.connector_id, True, "xero configured")
        return ConnectorHealth(
            self.connector_id,
            False,
            "Provider credentials are incomplete. Set QUICKBOOKS_REALM_ID or XERO_TENANT_ID.",
        )

    def _post_quickbooks(self, invoice_payload: dict[str, Any]) -> dict[str, Any]:
        token = self._quickbooks_token()
        realm_id = self._quickbooks_realm_id()
        customer_id = str(
            invoice_payload.get("customer_id")
            or invoice_payload.get("quickbooks_customer_id")
            or ""
        ).strip()
        if not customer_id:
            raise ConnectorError("QuickBooks requires `customer_id` (or `quickbooks_customer_id`).")

        line_items = self._line_items(invoice_payload)
        qbo_lines: list[dict[str, Any]] = []
        for line in line_items:
            amount = round(float(line["quantity"]) * float(line["unit_price"]), 2)
            detail: dict[str, Any] = {
                "Qty": line["quantity"],
                "UnitPrice": line["unit_price"],
            }
            if line["item_id"]:
                detail["ItemRef"] = {"value": line["item_id"]}
            qbo_lines.append(
                {
                    "DetailType": "SalesItemLineDetail",
                    "Amount": amount,
                    "Description": line["description"],
                    "SalesItemLineDetail": detail,
                }
            )

        payload: dict[str, Any] = {
            "CustomerRef": {"value": customer_id},
            "Line": qbo_lines,
            "DocNumber": str(invoice_payload.get("invoice_number") or ""),
        }
        due_date = str(invoice_payload.get("due_date") or "").strip()
        if due_date:
            payload["DueDate"] = due_date
        invoice_date = str(invoice_payload.get("invoice_date") or "").strip()
        if invoice_date:
            payload["TxnDate"] = invoice_date

        response = self.request_json(
            method="POST",
            url=f"https://quickbooks.api.intuit.com/v3/company/{realm_id}/invoice",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params={"minorversion": 75},
            payload=payload,
            timeout_seconds=35,
        )
        if not isinstance(response, dict):
            raise ConnectorError("QuickBooks API returned invalid response.")
        fault = response.get("Fault")
        if isinstance(fault, dict):
            raise ConnectorError(f"QuickBooks API error: {fault}")
        invoice = response.get("Invoice") or {}
        return {
            "provider": "quickbooks",
            "status": "accepted",
            "invoice_reference": invoice.get("DocNumber") or payload.get("DocNumber"),
            "invoice_id": invoice.get("Id"),
            "raw": response,
        }

    def _post_xero(self, invoice_payload: dict[str, Any]) -> dict[str, Any]:
        token = self._xero_token()
        tenant_id = self._xero_tenant_id()
        line_items = self._line_items(invoice_payload)
        xero_lines = [
            {
                "Description": line["description"],
                "Quantity": line["quantity"],
                "UnitAmount": line["unit_price"],
                "AccountCode": line["account_code"] or "200",
            }
            for line in line_items
        ]
        due_date = str(invoice_payload.get("due_date") or "").strip()
        invoice_date = str(invoice_payload.get("invoice_date") or "").strip() or date.today().isoformat()
        payload = {
            "Type": "ACCREC",
            "Contact": {"Name": str(invoice_payload.get("customer") or "Customer")},
            "LineItems": xero_lines,
            "Date": invoice_date,
            "DueDate": due_date or invoice_date,
            "Reference": str(invoice_payload.get("invoice_number") or ""),
            "Status": str(invoice_payload.get("status") or "DRAFT"),
            "CurrencyCode": str(invoice_payload.get("currency") or "USD"),
        }
        response = self.request_json(
            method="POST",
            url="https://api.xero.com/api.xro/2.0/Invoices",
            headers={
                "Authorization": f"Bearer {token}",
                "xero-tenant-id": tenant_id,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=35,
        )
        if not isinstance(response, dict):
            raise ConnectorError("Xero API returned invalid response.")
        invoices = response.get("Invoices") or []
        first = invoices[0] if isinstance(invoices, list) and invoices else {}
        return {
            "provider": "xero",
            "status": "accepted",
            "invoice_reference": first.get("InvoiceNumber") or payload.get("Reference"),
            "invoice_id": first.get("InvoiceID"),
            "raw": response,
        }

    def post_invoice(self, invoice_payload: dict[str, Any]) -> dict[str, Any]:
        preferred_provider = str(invoice_payload.get("provider") or "").strip().lower()
        if preferred_provider == "quickbooks":
            return self._post_quickbooks(invoice_payload)
        if preferred_provider == "xero":
            return self._post_xero(invoice_payload)

        quickbooks_ready = bool(
            self._read_secret("QUICKBOOKS_ACCESS_TOKEN") and self._read_secret("QUICKBOOKS_REALM_ID")
        )
        xero_ready = bool(self._read_secret("XERO_ACCESS_TOKEN") and self._read_secret("XERO_TENANT_ID"))
        if quickbooks_ready:
            return self._post_quickbooks(invoice_payload)
        if xero_ready:
            return self._post_xero(invoice_payload)
        raise ConnectorError(
            "No invoice provider is fully configured. Set QuickBooks or Xero credentials first."
        )
