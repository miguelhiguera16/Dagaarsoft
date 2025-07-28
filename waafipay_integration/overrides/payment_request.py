
import frappe
from frappe import _
from frappe.utils import flt
from erpnext.accounts.doctype.payment_request.payment_request import PaymentRequest
from erpnext.accounts.party import get_party_account, get_party_bank_account
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)
from waafipay_integration.waafipay.waafipay_client import generate_payment_link


class PaymentRequest(PaymentRequest):
	def on_submit(self):
		if self.payment_request_type == "Outward":
			self.db_set("status", "Initiated")
			return
		elif self.payment_request_type == "Inward":
			self.db_set("status", "Requested")

		send_mail = self.payment_gateway_validation() if self.payment_gateway else None
		ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)

		if (
			hasattr(ref_doc, "order_type") and getattr(ref_doc, "order_type") == "Shopping Cart"
		) or self.flags.mute_email:
			send_mail = False

		if send_mail and self.payment_channel != "Phone":
			self.set_payment_request_url()
			self.send_email()
			self.make_communication_entry()

		elif self.payment_channel == "Phone":
			generate_payment_link(self)


@frappe.whitelist(allow_guest=True)
def make_payment_request(**args):
	"""Make payment request"""

	args = frappe._dict(args)

	ref_doc = frappe.get_doc(args.dt, args.dn)
	gateway_account = get_gateway_details(args) or frappe._dict()

	grand_total = get_amount(ref_doc, gateway_account.get("payment_account"))
	if args.loyalty_points and args.dt == "Sales Order":
		from erpnext.accounts.doctype.loyalty_program.loyalty_program import validate_loyalty_points

		loyalty_amount = validate_loyalty_points(ref_doc, int(args.loyalty_points))
		frappe.db.set_value(
			"Sales Order", args.dn, "loyalty_points", int(args.loyalty_points), update_modified=False
		)
		frappe.db.set_value(
			"Sales Order", args.dn, "loyalty_amount", loyalty_amount, update_modified=False
		)
		grand_total = grand_total - loyalty_amount

	bank_account = (
		get_party_bank_account(args.get("party_type"), args.get("party"))
		if args.get("party_type")
		else ""
	)

	draft_payment_request = frappe.db.get_value(
		"Payment Request",
		{"reference_doctype": args.dt, "reference_name": args.dn, "docstatus": 0},
	)

	existing_payment_request_amount = get_existing_payment_request_amount(args.dt, args.dn)

	if existing_payment_request_amount:
		grand_total -= existing_payment_request_amount

	if draft_payment_request:
		frappe.db.set_value(
			"Payment Request", draft_payment_request, "grand_total", grand_total, update_modified=False
		)
		pr = frappe.get_doc("Payment Request", draft_payment_request)
	else:
		pr = frappe.new_doc("Payment Request")
		pr.update(
			{
				"payment_gateway_account": gateway_account.get("name"),
				"payment_gateway": gateway_account.get("payment_gateway"),
				"payment_account": gateway_account.get("payment_account"),
				"payment_channel": gateway_account.get("payment_channel"),
				"payment_request_type": args.get("payment_request_type"),
				"currency": ref_doc.currency,
				"grand_total": grand_total,
				"mode_of_payment": args.mode_of_payment,
				"email_to": args.recipient_id or ref_doc.owner,
				"subject": _("Payment Request for {0}").format(args.dn),
				"message": gateway_account.get("message") or get_dummy_message(ref_doc),
				"reference_doctype": args.dt,
				"reference_name": args.dn,
				"party_type": args.get("party_type") or "Customer",
				"party": args.get("party") or ref_doc.get("customer"),
				"bank_account": bank_account,
			}
		)

		# Update dimensions
		pr.update(
			{
				"cost_center": ref_doc.get("cost_center"),
				"project": ref_doc.get("project"),
			}
		)

		for dimension in get_accounting_dimensions():
			pr.update({dimension: ref_doc.get(dimension)})

		if args.order_type == "Shopping Cart" or args.mute_email:
			pr.flags.mute_email = True

		pr.insert(ignore_permissions=True)
		if args.submit_doc:
			pr.submit()

	if args.order_type == "Shopping Cart":
		frappe.db.commit()
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = pr.get_payment_url()

	if args.return_doc:
		return pr

	return pr.as_dict()


def get_gateway_details(args):  # nosemgrep
	"""Return gateway and payment account based on currency or default."""
	if args.get("payment_gateway_account"):
		return get_payment_gateway_account(args.get("payment_gateway_account"))

	if args.order_type == "Shopping Cart":
		payment_gateway_account = frappe.get_doc("E Commerce Settings").payment_gateway_account
		return get_payment_gateway_account(payment_gateway_account)

	# Try to get a gateway account that matches the document's currency
	if args.get("dt") and args.get("dn"):
		ref_doc = frappe.get_doc(args.get("dt"), args.get("dn"))
		currency = ref_doc.get("currency")
		if currency:
			account = frappe.db.get_value(
				"Payment Gateway Account",
				{"currency": currency},
				["name", "payment_gateway", "payment_account", "message", "payment_channel"],
				as_dict=True,
			)
			if account:
				return account

	# Fallback to default
	return get_payment_gateway_account({"is_default": 1})


def get_payment_gateway_account(args):
	return frappe.db.get_value(
		"Payment Gateway Account",
		args,
		["name", "payment_gateway", "payment_account", "message", "payment_channel"],
		as_dict=1,
	)


def get_amount(ref_doc, payment_account=None):
	"""get amount based on doctype"""
	dt = ref_doc.doctype
	if dt in ["Sales Order", "Purchase Order"]:
		grand_total = flt(ref_doc.rounded_total) or flt(ref_doc.grand_total)
	elif dt in ["Sales Invoice", "Purchase Invoice"]:
		if not ref_doc.get("is_pos"):
			if ref_doc.party_account_currency == ref_doc.currency:
				grand_total = flt(ref_doc.outstanding_amount)
			else:
				grand_total = flt(ref_doc.outstanding_amount) / ref_doc.conversion_rate
		elif dt == "Sales Invoice":
			for pay in ref_doc.payments:
				if pay.type == "Phone" and pay.account == payment_account:
					grand_total = pay.amount
					break
	elif dt == "POS Invoice":
		for pay in ref_doc.payments:
			if pay.type == "Phone" and pay.account == payment_account:
				grand_total = pay.amount
				break
	elif dt == "Fees":
		grand_total = ref_doc.outstanding_amount

	if grand_total > 0:
		return grand_total
	else:
		frappe.throw(_("Payment Entry is already created"))


def get_existing_payment_request_amount(ref_dt, ref_dn):
	"""
	Get the existing payment request which are unpaid or partially paid for payment channel other than Phone
	and get the summation of existing paid payment request for Phone payment channel.
	"""
	existing_payment_request_amount = frappe.db.sql(
		"""
		select sum(grand_total)
		from `tabPayment Request`
		where
			reference_doctype = %s
			and reference_name = %s
			and docstatus = 1
			and (status != 'Paid'
			or (payment_channel = 'Phone'
				and status = 'Paid'))
	""",
		(ref_dt, ref_dn),
	)
	return flt(existing_payment_request_amount[0][0]) if existing_payment_request_amount else 0


def get_dummy_message(doc):
	return frappe.render_template(
		"""{% if doc.contact_person -%}
<p>Dear {{ doc.contact_person }},</p>
{%- else %}<p>Hello,</p>{% endif %}

<p>{{ _("Requesting payment against {0} {1} for amount {2}").format(doc.doctype,
	doc.name, doc.get_formatted("grand_total")) }}</p>

<a href="{{ payment_url }}">{{ _("Make Payment") }}</a>

<p>{{ _("If you have any questions, please get back to us.") }}</p>

<p>{{ _("Thank you for your business!") }}</p>
""",
		dict(doc=doc, payment_url="{{ payment_url }}"),
	)
