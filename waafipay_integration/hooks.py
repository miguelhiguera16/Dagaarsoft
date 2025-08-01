from . import __version__ as app_version

app_name = "waafipay_integration"
app_title = "Waafipay Integration"
app_publisher = "Miguel Higuera"
app_description = "Frappe app for Waafiipay Integration"
app_email = "migueladolfohiguera@hotmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/waafipay_integration/css/waafipay_integration.css"
app_include_js = [
    # "/assets/waafipay_integration/js/waafipay_payment_handler.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/waafipay_integration/css/waafipay_integration.css"
# web_include_js = "/assets/waafipay_integration/js/waafipay_integration.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "waafipay_integration/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Payment Request" : "public/js/payment_request.js"
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#	"methods": "waafipay_integration.utils.jinja_methods",
#	"filters": "waafipay_integration.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "waafipay_integration.install.before_install"
# after_install = "waafipay_integration.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "waafipay_integration.uninstall.before_uninstall"
# after_uninstall = "waafipay_integration.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "waafipay_integration.utils.before_app_install"
# after_app_install = "waafipay_integration.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "waafipay_integration.utils.before_app_uninstall"
# after_app_uninstall = "waafipay_integration.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "waafipay_integration.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Payment Request": "waafipay_integration.overrides.payment_request.PaymentRequest",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Payment Request": {
        # "on_submit": "waafipay_integration.waafipay.waafipay_client.generate_payment_link",
    }
}


fixtures = [
    {
        "doctype": "Web Page",
        "filters": [
            [
                "name",
                "in",
                (
                    "waafipay-payment-success",
                    "waafipay-payment-failure",
                ),
            ]
        ],
    },
]


# Scheduled Tasks
# ---------------

# scheduler_events = {
#	"all": [
#		"waafipay_integration.tasks.all"
#	],
#	"daily": [
#		"waafipay_integration.tasks.daily"
#	],
#	"hourly": [
#		"waafipay_integration.tasks.hourly"
#	],
#	"weekly": [
#		"waafipay_integration.tasks.weekly"
#	],
#	"monthly": [
#		"waafipay_integration.tasks.monthly"
#	],
# }

# Testing
# -------

# before_tests = "waafipay_integration.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"waafipay/callback": "waafipay_integration.waafipay.api.callback",
    "erpnext.accounts.doctype.payment_request.payment_request.make_payment_request": "waafipay_integration.overrides.payment_request.make_payment_request",
    "posawesome.posawesome.api.posapp.create_payment_request": "waafipay_integration.api.create_payment_request",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "waafipay_integration.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["waafipay_integration.utils.before_request"]
# after_request = ["waafipay_integration.utils.after_request"]

# Job Events
# ----------
# before_job = ["waafipay_integration.utils.before_job"]
# after_job = ["waafipay_integration.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"waafipay_integration.auth.validate"
# ]

payment_gateway_controller = [
    "WaafiPay Settings=waafipay_integration.waafipay_integration.payment_gateways.waafipay.WaafiPaySettings"
]