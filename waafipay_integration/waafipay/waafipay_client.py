import frappe
from frappe.utils import flt
import requests
import uuid
import datetime
import json


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
    if not doc.create_payment_request:
        return

    if not doc.payment_gateway_account:
        return

    credentials = get_credentials(doc.payment_gateway_account)

    if not credentials:
        frappe.log_error(f"No credentials found for payment gateway account {doc.payment_gateway_account}", "WaafiPay Link Generation Failed")
        return

    if getattr(doc, "flags", None) and getattr(doc.flags, "only_get_payment_link", False):
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
            "hppSuccessCallbackUrl": credentials.success_callback_url,
            "hppFailureCallbackUrl": credentials.failure_callback_url,
            "hppRespDataFormat": 1,
            "transactionInfo": {
                "referenceId": doc.name,
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

    waafipay_log = frappe.new_doc("WaafiPay Log")
    waafipay_log.update({
        "status": "Initiated",
        "request_payload": frappe.as_json(payload),
        "response_data": frappe.as_json(response.json()),
    })
    waafipay_log.flags.ignore_permissions = True
    waafipay_log.save()

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("responseCode") == "2001":
            doc.waafipay_payment_link = res_json["params"].get("hppUrl") or res_json["params"].get("directPaymentLink")
            doc.db_update()

            waafipay_log.status = "Success"
            waafipay_log.db_update()
        else:
            frappe.log_error(
                frappe.as_json({
                    "error": "Unexpected response from WaafiPay",
                    "response": res_json
                }),
                "WaafiPay Link Generation Failed"
            )

            waafipay_log.status = "Failed"
            waafipay_log.db_update()
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


@frappe.whitelist(allow_guest=True)
def callback(**kwargs):
    pass


@frappe.whitelist(allow_guest=True)
def payment_received(**kwargs):
    waafipay_log = None

    if kwargs.get("responseCode") == "2001":
        waafipay_log = frappe.new_doc("WaafiPay Log")
        waafipay_log.flags.ignore_permissions = True
        # create waafipay log
        waafipay_log.update({
            "status": "Initiated",
            "request_payload": frappe.as_json(kwargs),
            "response_data": frappe.as_json(kwargs),
        })
        waafipay_log.save()

        payment_request = kwargs.get("params").get("referenceId") if kwargs.get("params") else None
        if not payment_request:
            payment_request = kwargs.get("referenceId")
        
        if payment_request:
            if frappe.db.exists("Payment Request", payment_request):
                try:
                    payment_request = frappe.get_doc("Payment Request", payment_request)
                    try:
                        payment_request.create_payment_entry()
                    except Exception as e:
                        waafipay_log.status = "Failed"
                        waafipay_log.error_message = e
                        waafipay_log.db_update()
                        frappe.local.response["type"] = "redirect"
                        frappe.local.response["location"] = "/waafipay-payment-failure"
                        return
                    else:
                        waafipay_log.status = "Success"
                        waafipay_log.db_update()
                        frappe.local.response["type"] = "redirect"
                        frappe.local.response["location"] = "/waafipay-payment-success"
                        return
                except Exception as e:
                    waafipay_log.status = "Failed"
                    waafipay_log.error_message = e
                    waafipay_log.db_update()
        else:
            # If no Payment Request but we have a transaction ID (from preauthorization), attempt to commit it
            transaction_id = kwargs.get("params", {}).get("transactionId") or kwargs.get("transactionId")
            if transaction_id:
                try:
                    client = WaafiPayClient("WaafiPay")
                    commit_response = client.commit_authorized_payment(transaction_id)

                    if commit_response.get("responseCode") == "2001":
                        waafipay_log.status = "Success"
                        waafipay_log.db_update()

                        # Attempt to find and submit related Payment Request
                        payment_request_doc = frappe.get_doc("Payment Request", payment_request)
                        payment_request_doc.flags.ignore_permissions = True
                        try:
                            payment_request_doc.create_payment_entry()
                        except Exception as e:
                            waafipay_log.status = "Failed"
                            waafipay_log.error_message = str(e)
                            waafipay_log.db_update()
                            frappe.local.response["type"] = "redirect"
                            frappe.local.response["location"] = "/waafipay-payment-failure"
                            return
                        else:
                            frappe.local.response["type"] = "redirect"
                            frappe.local.response["location"] = "/waafipay-payment-success"
                            return
                except Exception as e:
                    waafipay_log.status = "Failed"
                    waafipay_log.error_message = str(e)
                    waafipay_log.db_update()
                    frappe.local.response["type"] = "redirect"
                    frappe.local.response["location"] = "/waafipay-payment-failure"
                    return
            else:
                waafipay_log.status = "Failed"
                waafipay_log.error_message = f"Payment Request {payment_request} not found"
                waafipay_log.db_update()
                return

    else:
        if not waafipay_log:
            waafipay_log = frappe.new_doc("WaafiPay Log")
            waafipay_log.flags.ignore_permissions = True

        waafipay_log.update({
            "status": "Failed",
            "request_payload": frappe.as_json(kwargs),
            "response_data": frappe.as_json(kwargs),
            "error_message": kwargs.get("responseMsg"),
        })
        waafipay_log.save()
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = "/waafipay-payment-failure"
        return


@frappe.whitelist(allow_guest=True)
def try_again(log_name):
    log = frappe.get_doc("WaafiPay Log", log_name)
    log.flags.ignore_permissions = True

    if not log.request_payload:
        frappe.throw("No request payload found")

    if not log.response_data:
        frappe.throw("No response data found")

    # cmd = log.response_data.get("cmd")
    response_data = json.loads(log.response_data)
    reference_id = response_data.get("referenceId")

    # if not cmd:
    #     frappe.throw("Command not found")

    # if not reference_id:
    #     frappe.throw("Reference ID not found")

    payment_request = frappe.get_doc("Payment Request", reference_id)
    payment_request.flags.ignore_permissions = True

    try:
        payment_request.create_payment_entry()
    except Exception as e:
        frappe.throw(e)
    else:
        log.status = "Success"
        log.db_update()


@frappe.whitelist(allow_guest=True)
def failure_callback(**kwargs):
    
    # create waafipay log
    waafipay_log = frappe.new_doc("WaafiPay Log")
    waafipay_log.update({
        "status": "Failed",
        "request_payload": frappe.as_json(kwargs),
        "response_data": frappe.as_json(kwargs),
        "error_message": kwargs.get("responseMsg"),
    })
    waafipay_log.flags.ignore_permissions = True
    waafipay_log.save()


    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = "/waafipay-payment-failure"
    return
