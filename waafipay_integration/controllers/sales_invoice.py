import frappe
from waafipay_integration.waafipay.waafipay_client import WaafiPayClient

def on_submit(doc, method=None):
    pass
    # make_waafipay_payment(doc)


def make_waafipay_payment(doc):
    settings = get_settings()
    supported_modes = [mode.mode_of_payment for mode in settings.waafipay_modes or []]

    client = WaafiPayClient()
    phone_number = get_phone_number(doc) or "252611111111"

    waafipay_payments = [p for p in doc.payments if p.mode_of_payment in supported_modes]

    if not waafipay_payments:
        frappe.msgprint("Payment skipped: No compatible WaafiPay payment methods found.")
        return

    for payment in waafipay_payments:
        amount = float(payment.amount or 0)

        # Crear log inicial
        payload = {}
        log_doc = create_waafipay_log(doc, payload)

        # Generar payload
        payload = client._generate_common_payload()
        payload["serviceName"] = "API_PREAUTHORIZE"
        payload["serviceParams"] = {
            "merchantUid": client.merchant_uid,
            "apiUserId": client.api_user_id,
            "apiKey": client.api_key,
            "paymentMethod": "MWALLET_ACCOUNT",
            "payerInfo": {
                "accountNo": phone_number
            },
            "transactionInfo": {
                "referenceId": str(frappe.generate_hash()),
                "invoiceId": doc.name,
                "amount": f"{amount:.2f}",
                "currency": "USD",
                "description": f"Payment for Sales Invoice {doc.name} via {payment.mode_of_payment}"
            }
        }

        log_doc.request_payload = frappe.as_json(payload)
        log_doc.save(ignore_permissions=True)

        try:
            response = client.preauthorize_payment(phone_number, amount)
        except Exception as e:
            log_doc.status = "Failed"
            log_doc.response_data = frappe.as_json({"error": str(e)})
            log_doc.save(ignore_permissions=True)
            frappe.throw(f"WaafiPay payment request failed for {payment.mode_of_payment}: {e}")

        status = "Success" if response.get("responseCode") == "2001" else "Failed"
        update_waafipay_log(log_doc, response)

        # Opcional: guardar último resultado en el invoice
        doc.db_set("waafipay_reference_id", response.get("referenceId", ""), update_modified=False)
        # doc.db_set("waafipay_log", log_doc.name, update_modified=False)

        frappe.msgprint(f"WaafiPay ({payment.mode_of_payment}) Response:\n{response}")

def create_waafipay_log(doc, payload):
    doctype = "WaafiPay Log"
    
    doc = frappe.new_doc(doctype)
    doc.update({
        "sales_invoice": doc.name,
        "status": "Initiated",
        "request_payload": frappe.as_json(payload),
        "reference_id": payload.get("serviceParams", {}).get("transactionInfo", {}).get("referenceId"),
    })
    doc.save()

    return doc


def update_waafipay_log(doc, response):
    doctype = "WaafiPay Log"
    doc = frappe.get_doc(doctype, doc.name)
    doc.update({
        "status": "Success" if response.get("responseCode") == "2001" else "Failed",
        "response_data": frappe.as_json(response)
    })
    doc.save()


def get_phone_number(doc):
    doctype = "Customer"

    doc = frappe.get_doc(doctype, doc.customer)
    return doc.mobile_no


def get_settings():
    return frappe.get_single("WaafiPay Settings")