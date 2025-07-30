import json
import frappe
import requests
import datetime
import uuid
from frappe import _
from frappe.utils import flt
from erpnext.setup.utils import get_exchange_rate

from posawesome.posawesome.api.posapp import (
    get_existing_payment_request, 
    get_new_payment_request,
)


@frappe.whitelist(allow_guest=True)
def create_payment_request(doc):
    doc = json.loads(doc)
    for pay in doc.get("payments"):
        if pay.get("type") == "Phone":
            if pay.get("amount") <= 0:
                frappe.throw(_("Payment amount cannot be less than or equal to 0"))

            if not doc.get("contact_mobile"):
                frappe.throw(_("Please enter the phone number first"))

            pay_req = get_existing_payment_request(doc, pay)
            if not pay_req:
                pay_req = get_new_payment_request(doc, pay)
                pay_req.submit()
            else:
                pay_req.request_phone_payment()

            preauthorize_payment(
                pay_req.payment_gateway_account,
                pay.get("contact_mobile") or doc.get("contact_mobile"),
                pay.get("amount"),
                doc.get("currency"),
                pay.get("mode_of_payment"),
                doc.get("name"),
            )

            return pay_req


def preauthorize_payment(payment_gateway_account, phone_number, amount, currency, mode_of_payment, invoice_id=None):
    # convert values to string
    phone_number = str(phone_number)
    amount = flt(amount, 2)
    currency = str(currency)
    invoice_id = str(invoice_id)
    mode_of_payment = str(mode_of_payment)

    payment_gateway_value = frappe.get_value("Payment Gateway Account", payment_gateway_account, "payment_gateway")
    payment_gateway = frappe.get_doc("Payment Gateway", payment_gateway_value)

    credentials = frappe.get_doc(payment_gateway.gateway_settings, payment_gateway.gateway_controller)

    if not credentials:
        frappe.throw(_(f"Credentials not found for {payment_gateway_account}"))

    allowed_currencies = [c.currency for c in credentials.supported_currencies]

    if currency not in allowed_currencies:
        frappe.throw(f"Currency <b>{currency}</b> is not supported by this gateway <b>{payment_gateway_account}</b>.")

    payload = {
        "schemaVersion": "1.0",
        "requestId": str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channelName": "WEB",
        "serviceName": "API_PREAUTHORIZE",
        "serviceParams": {
            "merchantUid": credentials.merchant_uid,
            "apiUserId": credentials.api_user_id,
            "apiKey": credentials.get_password("api_key"),
            "paymentMethod": "MWALLET_ACCOUNT",
            "payerInfo": {
                "accountNo": phone_number
            },
            "transactionInfo": {
                "invoiceId": invoice_id or f"INV-{str(uuid.uuid4())[:8]}",
                "referenceId": invoice_id or str(uuid.uuid4()),
                "amount": f"{amount:.2f}",
                "currency": currency,
                "description": f"Payment for Sales Invoice {invoice_id}",
            }
        }
    }

    if invoice_id:
        payload["serviceParams"]["transactionInfo"]["invoiceId"] = invoice_id

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = requests.post(f"{credentials.api_base_url}/asm", json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()

        # create log
        log = frappe.get_doc({
            "doctype": "WaafiPay Log",
            "reference_id": response_data.get("referenceId"),
            "status": "Success" if response_data.get("responseCode") == "2001" else "Failed",
            "request_payload": json.dumps(payload),
            "response_data": json.dumps(response_data),
        })
        log.flags.ignore_permissions = True
        log.save()


    except requests.RequestException as e:
        frappe.throw(_("Error during payment request: {0}").format(str(e)))

    finally:
        log = frappe.get_doc({
            "doctype": "WaafiPay Log",
            "reference_id": response_data.get("referenceId"),
            "status": "Success" if response_data.get("responseCode") == "2001" else "Failed",
            "request_payload": json.dumps(payload),
            "response_data": json.dumps(response_data),
        })
        log.flags.ignore_permissions = True
        log.save()

    if response_data.get("responseCode") == "2001" and response_data.get("errorCode") == "0":
        state = response_data.get("params", {}).get("state")
        if state in ("APPROVED", "RCS_SUCCESS"):
            commit_status, commit_response = make_preauthorize_commit(
                payment_gateway_account,
                response_data.get("params", {}).get("transactionId")
            )
            if commit_response.get("responseCode") == "2001" or commit_response.get('responseMsg') == "RCS_SUCCESS":
                payment_request = get_payment_request(invoice_id)
                payment_request.status = "Paid"
                payment_request.db_update()
                return payment_request
            else:
                frappe.log_error("Error during commit payment", f"Commit payment failed: {response_data.get('responseMsg')}")
                log.status = "Failed"
                log.response_data = json.dumps(response_data)
                log.flags.ignore_permissions = True
                log.save()
    
                frappe.throw(f"Commit payment failed: {commit_response.get('responseMsg')}")
        else:
            log.status = "Failed"
            log.response_data = json.dumps(response_data)
            log.flags.ignore_permissions = True
            log.save()

            frappe.throw(_("Payment not approved: {0}").format(state or "No state info"))
    else:
        log.status = "Failed"
        log.response_data = json.dumps(response_data)
        log.flags.ignore_permissions = True
        log.save()
        frappe.throw(_("Payment gateway error: {0}").format(response_data.get("responseMsg") or "Unknown error"))



def make_preauthorize_commit(payment_gateway_account, invoice_id):
    payment_gateway_value = frappe.get_value("Payment Gateway Account", payment_gateway_account, "payment_gateway")
    payment_gateway = frappe.get_doc("Payment Gateway", payment_gateway_value)

    credentials = frappe.get_doc(payment_gateway.gateway_settings, payment_gateway.gateway_controller)

    if not credentials:
        frappe.throw(_(f"Credentials not found for {payment_gateway_account}"))

    payload = {
        "schemaVersion": "1.0",
        "requestId": str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channelName": "WEB",
        "serviceName": "API_PREAUTHORIZE_COMMIT",
        "serviceParams": {
            "merchantUid": credentials.merchant_uid,
            "apiUserId": credentials.api_user_id,
            "apiKey": credentials.get_password("api_key"),
            "transactionId": invoice_id,
            "description": f"Order #{invoice_id} committed"
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = requests.post(f"{credentials.api_base_url}/asm", json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()

        # create log
        log = frappe.get_doc({
            "doctype": "WaafiPay Log",
            "reference_id": response_data.get("referenceId"),
            "status": "Success" if response_data.get("responseCode") == "2001" else "Failed",
            "request_payload": json.dumps(payload),
            "response_data": json.dumps(response_data),
        })
        log.flags.ignore_permissions = True
        log.save()

    except requests.RequestException as e:
        log.status = "Failed"
        log.response_data = json.dumps(response_data)
        log.save()
        frappe.throw(_("Error during payment request: {0}").format(str(e)))

    return response_data.get("responseCode") in ["2001"], response_data



def get_sales_invoice(invoice_name):
    doctype = "Sales Invoice"

    if name:= frappe.db.exists(doctype, invoice_name):
        return frappe.get_doc(doctype, name)


def get_payment_request(invoice_id):
    doctype = "Payment Request"
    filters = {
        "reference_doctype": "Sales Invoice",
        "reference_name": invoice_id,
    }

    if name:= frappe.db.exists(doctype, filters):
        return frappe.get_doc(doctype, name)

    return frappe.throw(_(f"Payment Request not found for invoice <b>{invoice_id}</b>"))


@frappe.whitelist(allow_guest=True)
def callback(**kwargs):
    return

# @frappe.whitelist(allow_guest=True)
# def callback():
#     frappe.set_user("Administrator")
#     try:
#         data = frappe.local.form_dict or json.loads(frappe.request.data)
#         frappe.logger("waafipay").info(f"Received callback data: {data}")

#         reference_id = data.get("referenceId") or data.get("params", {}).get("referenceId")
#         status = data.get("status") or data.get("responseCode") or data.get("params", {}).get("state")
#         order_id = data.get("params", {}).get("orderId")
#         amount = flt(data.get("params", {}).get("txAmount") or data.get("amount") or 0, 2)

#         if not reference_id:
#             frappe.throw(_("Missing reference ID in callback"))

#         # Buscar log
#         log = frappe.get_doc("WaafiPay Log", {"reference_id": reference_id})
#         log.status = "Success" if status == "2001" or status == "APPROVED" else "Failed"
#         log.response_data = frappe.as_json(data)
#         log.save(ignore_permissions=True)

#         # Obtener la factura desde el log
#         if not log.sales_invoice:
#             frappe.throw(_("No Sales Invoice linked to this log entry"))

#         invoice = frappe.get_doc("Sales Invoice", log.sales_invoice)

#         mode_of_payment = log.mode_of_payment
#         if mode_of_payment:
#             invoice.set("payments", [])
#             mode_payment_exists = any(p.mode_of_payment == mode_of_payment for p in invoice.payments or [])
#             if not mode_payment_exists:
#                 invoice.append("payments", {
#                     "mode_of_payment": mode_of_payment,
#                     "amount": 0.0
#                 })
#                 invoice.paid_amount = 0.0
    
#         if invoice.docstatus == 0:
#             invoice.flags.ignore_permissions = True
#             invoice.submit()

#         # Obtener moneda base y moneda del pago
#         company_currency = invoice.company_currency
#         payment_currency = data.get("currency") or "USD"

#         # Obtener modo de pago y moneda de la cuenta contable
#         payment_account = None
#         account_currency = company_currency  # Por defecto

#         if mode_of_payment:
#             mop_doc = frappe.get_doc("Mode of Payment", mode_of_payment)
#             # Buscar cuenta para la compañía de la factura
#             account_row = next((row for row in mop_doc.accounts if row.company == invoice.company), None)
#             if account_row:
#                 payment_account = account_row.default_account
#                 if payment_account:
#                     account_doc = frappe.get_doc("Account", payment_account)
#                     account_currency = account_doc.account_currency or company_currency

#         # Calcular tasas de cambio
#         source_exchange_rate = 1.0
#         target_exchange_rate = 1.0

#         if account_currency != company_currency:
#             source_exchange_rate = get_exchange_rate(account_currency, company_currency, invoice.posting_date)

#         if payment_currency != company_currency:
#             target_exchange_rate = get_exchange_rate(payment_currency, company_currency, invoice.posting_date)

#         # Crear Payment Entry si no existe
#         if not frappe.db.exists("Payment Entry", {"reference_no": reference_id, "reference_date": invoice.posting_date}):
#             payment_entry = frappe.get_doc({"doctype": "Payment Entry"})
#             payment_entry.update({
#                 "payment_type": "Receive",
#                 "company": invoice.company,
#                 "posting_date": invoice.posting_date,
#                 "mode_of_payment": mode_of_payment,
#                 "party_type": "Customer",
#                 "party": invoice.customer,
#                 "paid_amount": amount,
#                 "received_amount": amount,
#                 "paid_currency": payment_currency,
#                 "source_exchange_rate": flt(source_exchange_rate, 2),
#                 "target_exchange_rate": flt(target_exchange_rate, 2),
#                 "reference_no": reference_id,
#                 "reference_date": invoice.posting_date,
#                 "paid_to": invoice.debit_to,
#                 "references": [{
#                     "reference_doctype": "Sales Invoice",
#                     "reference_name": invoice.name,
#                     "total_amount": invoice.outstanding_amount,
#                     "outstanding_amount": invoice.outstanding_amount,
#                     "allocated_amount": amount,
#                 }]
#             })
#             payment_entry.flags.ignore_permissions = True
#             payment_entry.submit()

#         return {"message": "Callback processed successfully."}

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "WaafiPay Callback Error")
#         return {"error": str(e)}
