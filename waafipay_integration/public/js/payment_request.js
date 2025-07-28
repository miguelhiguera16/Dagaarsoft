frappe.ui.form.on("Payment Request", {
    copy_waafipay_payment_link: function(frm) {
        frappe.utils.copy_to_clipboard(frm.doc.waafipay_payment_link);
    },
    open_waafipay_payment_link: function(frm) {
        window.open(frm.doc.waafipay_payment_link, "_blank");
    }
});