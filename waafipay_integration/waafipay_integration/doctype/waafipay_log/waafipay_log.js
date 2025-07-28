// Copyright (c) 2025, Miguel Higuera and contributors
// For license information, please see license.txt

frappe.ui.form.on('WaafiPay Log', {
	refresh: function(frm) {
		frm.trigger("add_custom_buttons");
	},
	add_custom_buttons: function(frm) {
		frm.trigger("add_try_again_button");
	},
	add_try_again_button: function(frm) {
		const { doc } = frm;

		if (doc.status == "Failed" || doc.status == "Initiated" || doc.status == "Error") {
			const button_label = "Try Again";
			const button_function = function() {
				const method = "waafipay_integration.waafipay.waafipay_client.try_again";
				const args = {
					"log_name": doc.name
				}
				const callback = function(r) {
					frm.reload_doc();
				}

				frappe.call(method, args, callback);

			};

			frm.add_custom_button(button_label, button_function).addClass("btn-primary");
		}
	},
	
});
