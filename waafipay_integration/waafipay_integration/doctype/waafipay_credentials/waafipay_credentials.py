# Copyright (c) 2025, Miguel Higuera and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document
from waafipay_integration.waafipay.waafipay_client import WaafiPayClient


class WaafiPayCredentials(Document):
    def validate_transaction_currency(self, currency):
        # Get supported currencies from the supported_currencies table
        supported_currencies = [row.currency for row in self.supported_currencies]
        
        if currency not in supported_currencies:
            frappe.throw(f"Currency {currency} not supported by WaafiPay")

    def request_for_payment(self, **kwargs):
        """
        Ejecutado cuando se presiona el botón Request en POS
        invoice_doc: dict o Document del Sales Invoice con pagos y datos
        """
        sales_invoice = kwargs.get("payment_reference")

        invoice_doc = self.get_sales_invoice(sales_invoice)

        self.validate_transaction_currency(invoice_doc.currency)

        client = WaafiPayClient(self.name)

        phone_number = None
        # Get customer phone number
        if invoice_doc.customer:
            customer = frappe.get_doc("Customer", invoice_doc.customer)
            phone_number = customer.mobile_no or customer.phone_no

        if not phone_number:
            frappe.throw("Customer phone number is required for WaafiPay payment")

        # Find the WaafiPay payment method
        waafipay_payment = None
        supported_modes = [m.mode_of_payment for m in self.waafipay_modes]
        for p in invoice_doc.payments:
            if p.mode_of_payment in supported_modes:
                waafipay_payment = p
                break

        if not waafipay_payment:
            frappe.throw("No compatible WaafiPay payment method found")

        amount = float(waafipay_payment.amount)

        # Create initial log
        log_doc = self.create_waafipay_log(
            sales_invoice=invoice_doc.name,
            status="Initiated",
            request_payload={}
        )

        # Prepare payload according to WaafiPay docs
        payload = client._generate_common_payload()
        payload.update({
            "serviceName": "API_PREAUTHORIZE",
            "serviceParams": {
                "merchantUid": client.merchant_uid,
                "apiUserId": client.api_user_id,
                "apiKey": client.api_key,
                "paymentMethod": "MWALLET_ACCOUNT",
                "payerInfo": {
                    "accountNo": phone_number
                },
                "transactionInfo": {
                    "referenceId": log_doc.name,
                    "invoiceId": invoice_doc.name,
                    "amount": f"{amount:.2f}",
                    "currency": invoice_doc.currency,
                    "description": f"Payment for Sales Invoice {invoice_doc.name} via WaafiPay"
                }
            }
        })

        log_doc.request_payload = frappe.as_json(payload)
        log_doc.save(ignore_permissions=True)

        # Send payment
        try:
            response = client.preauthorize_payment(phone_number, amount, invoice_doc.currency, invoice_doc.name)
        except Exception as e:
            log_doc.status = "Failed"
            log_doc.response_data = frappe.as_json({"error": str(e)})
            log_doc.save(ignore_permissions=True)
            frappe.throw(f"WaafiPay payment request failed: {e}")

        status = "Success" if response.get("responseCode") == "2001" else "Failed"
        log_doc.status = status
        log_doc.response_data = frappe.as_json(response)
        log_doc.save(ignore_permissions=True)

        # Save reference in invoice
        invoice_doc.db_set("waafipay_reference_id", response.get("referenceId", ""), update_modified=False)

        if status == "Success":
            try:
                # Limpiar tabla payments para que no tenga pagos con monto > 0
                invoice_doc.payments = []
                # Agregar modo de pago actual con monto 0
                invoice_doc.append("payments", {
                    "mode_of_payment": waafipay_payment.mode_of_payment,
                    "amount": 0.0,
                })
                invoice_doc.submit()
            except Exception as e:
                frappe.throw(f"Error submitting invoice: {e}")
            else:
                frappe.msgprint("Payment request sent successfully")

        # Return response for frontend
        return {
            "status": status,
            "message": response.get("responseMessage", ""),
            "reference_id": response.get("referenceId", "")
        }

    def create_waafipay_log(self, **kwargs):
        doc = frappe.new_doc("WaafiPay Log")
        request_payload = kwargs.get("request_payload")
        response_data = kwargs.get("response_data")

        if request_payload is None:
            request_payload_str = None
        elif isinstance(request_payload, str):
            request_payload_str = request_payload
        else:
            request_payload_str = json.dumps(request_payload)

        if response_data is None:
            response_data_str = None
        elif isinstance(response_data, str):
            response_data_str = response_data
        else:
            response_data_str = json.dumps(response_data)

        doc.update({
            "status": kwargs.get("status"),
            "request_payload": request_payload_str,
            "response_data": response_data_str,
            "sales_invoice": kwargs.get("sales_invoice"),
            "mode_of_payment": kwargs.get("mode_of_payment"),
            "reference_id": doc.name,
        })
        doc.save()
        return doc

    def get_sales_invoice(self, sales_invoice):
        doctype = "Sales Invoice"

        if frappe.db.exists(doctype, sales_invoice):
            return frappe.get_doc(doctype, sales_invoice)
