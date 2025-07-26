import frappe
from frappe.utils import flt
import requests
import uuid
import datetime


class WaafiPayClient:
    def __init__(self, credentials_name):
        self.settings = frappe.get_doc("WaafiPay Credentials", credentials_name)
        self.merchant_uid = self.settings.merchant_uid
        self.api_user_id = self.settings.api_user_id
        self.api_key = self.settings.get_password("api_key")
        self.base_url = self.settings.api_base_url or "https://api.waafipay.com"
        self.supported_currencies = [row.currency for row in self.settings.supported_currencies]

    def _generate_common_payload(self):
        return {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "merchantUid": self.merchant_uid,
            "apiUserId": self.api_user_id,
            "apiKey": self.api_key,
        }

    def preauthorize_payment(self, phone_number, amount, currency, invoice_id=None):
        if currency not in self.supported_currencies:
            frappe.throw(f"Currency '{currency}' is not supported by this gateway.")

        payload = {
            "schemaVersion": "1.0",
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "channelName": "WEB",
            "serviceName": "API_PREAUTHORIZE",
            "serviceParams": {
                "merchantUid": self.merchant_uid,
                "apiUserId": self.api_user_id,
                "apiKey": self.api_key,
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
        response = requests.post(f"{self.base_url}/asm", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def generate_payment_link(doc, method=None):
    if not doc.payment_gateway_account:
        return

    credentials = get_credentials(doc.payment_gateway_account)

    if not credentials:
        frappe.log_error(f"No credentials found for payment gateway account {doc.payment_gateway_account}", "WaafiPay Link Generation Failed")
        return

    payload = {
        "schemaVersion": "1.0",
        "requestId": str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channelName": "WEB",
        "serviceName": "HPP_PURCHASE",
        "serviceParams": {
            "merchantUid": credentials.merchant_uid,
            "storeId": credentials.store_id,
            "hppKey": credentials.get_password("hpp_key"),
            "paymentMethod": "MWALLET_ACCOUNT",
            # "hppSuccessCallbackUrl": success_url,
            # "hppFailureCallbackUrl": failure_url,
            "hppRespDataFormat": 1,
            "transactionInfo": {
                "referenceId": doc.reference_name,
                "amount": flt(doc.grand_total),
                "currency": doc.currency,
                "description": f"Payment for {doc.grand_total} {doc.currency} for {doc.reference_name}"
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    response = requests.post(f"{credentials.api_base_url}/asm", json=payload, headers=headers)

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("responseCode") == "2001":
            doc.waafipay_payment_link = res_json["params"].get("hppUrl") or res_json["params"].get("directPaymentLink")
            doc.db_update()
        else:
            frappe.log_error(
                frappe.as_json({
                    "error": "Unexpected response from WaafiPay",
                    "response": res_json
                }),
                "WaafiPay Link Generation Failed"
            )
    else:
        frappe.log_error(response.text, "WaafiPay Link Generation HTTP Error")
    response.raise_for_status()
    return response.json()


def get_credentials(payment_gateway_account):
    payment_gateway = frappe.get_value("Payment Gateway Account", payment_gateway_account, "payment_gateway")

    if payment_gateway:
        gateway_controller = frappe.get_value("Payment Gateway", payment_gateway, "gateway_controller")

        if gateway_controller:
            return frappe.get_doc("WaafiPay Credentials", gateway_controller)

    return None
