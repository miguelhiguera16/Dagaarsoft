import json
import frappe
from frappe import _
from frappe.utils import flt
from waafipay_integration.controllers.sales_invoice import make_waafipay_payment


@frappe.whitelist()
def request_phone_payment(invoice_name, phone=None):
    try:
        doc = get_sales_invoice(invoice_name)

        # Override phone if provided
        if phone:
            doc.customer_mobile = phone # optional if you want to pass it
        make_waafipay_payment(doc)

        return {
            "status": "Success",
            "message": f"Phone payment requested for invoice {invoice_name}"
        }

    except Exception as e:
        frappe.log_error("Error in request_phone_payment", e)
        return {
            "status": "Failed",
            "message": str(e)
        }


def get_sales_invoice(invoice_name):
    doctype = "Sales Invoice"

    if name:= frappe.db.exists(doctype, invoice_name):
        return frappe.get_doc(doctype, name)


from erpnext.setup.utils import get_exchange_rate
from frappe.utils import flt

@frappe.whitelist(allow_guest=True)
def callback():
    frappe.set_user("Administrator")
    try:
        data = frappe.local.form_dict or json.loads(frappe.request.data)
        frappe.logger("waafipay").info(f"Received callback data: {data}")

        reference_id = data.get("referenceId") or data.get("params", {}).get("referenceId")
        status = data.get("status") or data.get("responseCode") or data.get("params", {}).get("state")
        order_id = data.get("params", {}).get("orderId")
        amount = flt(data.get("params", {}).get("txAmount") or data.get("amount") or 0, 2)

        if not reference_id:
            frappe.throw(_("Missing reference ID in callback"))

        # Buscar log
        log = frappe.get_doc("WaafiPay Log", {"reference_id": reference_id})
        log.status = "Success" if status == "2001" or status == "APPROVED" else "Failed"
        log.response_data = frappe.as_json(data)
        log.save(ignore_permissions=True)

        # Obtener la factura desde el log
        if not log.sales_invoice:
            frappe.throw(_("No Sales Invoice linked to this log entry"))

        invoice = frappe.get_doc("Sales Invoice", log.sales_invoice)

        mode_of_payment = log.mode_of_payment
        if mode_of_payment:
            invoice.set("payments", [])
            mode_payment_exists = any(p.mode_of_payment == mode_of_payment for p in invoice.payments or [])
            if not mode_payment_exists:
                invoice.append("payments", {
                    "mode_of_payment": mode_of_payment,
                    "amount": 0.0
                })
                invoice.paid_amount = 0.0
    
        if invoice.docstatus == 0:
            invoice.flags.ignore_permissions = True
            invoice.submit()

        # Obtener moneda base y moneda del pago
        company_currency = invoice.company_currency
        payment_currency = data.get("currency") or "USD"

        # Obtener modo de pago y moneda de la cuenta contable
        payment_account = None
        account_currency = company_currency  # Por defecto

        if mode_of_payment:
            mop_doc = frappe.get_doc("Mode of Payment", mode_of_payment)
            # Buscar cuenta para la compañía de la factura
            account_row = next((row for row in mop_doc.accounts if row.company == invoice.company), None)
            if account_row:
                payment_account = account_row.default_account
                if payment_account:
                    account_doc = frappe.get_doc("Account", payment_account)
                    account_currency = account_doc.account_currency or company_currency

        # Calcular tasas de cambio
        source_exchange_rate = 1.0
        target_exchange_rate = 1.0

        if account_currency != company_currency:
            source_exchange_rate = get_exchange_rate(account_currency, company_currency, invoice.posting_date)

        if payment_currency != company_currency:
            target_exchange_rate = get_exchange_rate(payment_currency, company_currency, invoice.posting_date)

        # Crear Payment Entry si no existe
        if not frappe.db.exists("Payment Entry", {"reference_no": reference_id, "reference_date": invoice.posting_date}):
            payment_entry = frappe.get_doc({"doctype": "Payment Entry"})
            payment_entry.update({
                "payment_type": "Receive",
                "company": invoice.company,
                "posting_date": invoice.posting_date,
                "mode_of_payment": mode_of_payment,
                "party_type": "Customer",
                "party": invoice.customer,
                "paid_amount": amount,
                "received_amount": amount,
                "paid_currency": payment_currency,
                "source_exchange_rate": flt(source_exchange_rate, 2),
                "target_exchange_rate": flt(target_exchange_rate, 2),
                "reference_no": reference_id,
                "reference_date": invoice.posting_date,
                "paid_to": invoice.debit_to,
                "references": [{
                    "reference_doctype": "Sales Invoice",
                    "reference_name": invoice.name,
                    "total_amount": invoice.outstanding_amount,
                    "outstanding_amount": invoice.outstanding_amount,
                    "allocated_amount": amount,
                }]
            })
            payment_entry.flags.ignore_permissions = True
            payment_entry.submit()

        return {"message": "Callback processed successfully."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "WaafiPay Callback Error")
        return {"error": str(e)}
