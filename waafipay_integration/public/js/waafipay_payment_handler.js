// evntBus.$on("payment_method_selected", async (payment_method) => {
//   console.log("Handler cargado, pago seleccionado:", payment_method);
//   if (["SAHAL", "ZAAD", "EVC"].includes(payment_method)) {
//     console.log("Phone payment method selected:", payment_method);
//     const amount_due = pos.invoice_doc.grand_total;

//     // Realizar el request a tu backend para API_PREAUTHORIZE
//     const r = await frappe.call({
//       method: "waafipay_integration.api.request_phone_payment",
//       args: {
//         invoice_name: pos.invoice_doc.name,
//         payment_method: payment_method
//       }
//     });

//     console.log("Response from request_phone_payment:", r);

//     if (r.message && r.message.status === "Success") {
//       // Agregar el pago
//       evntBus.$emit("append_payment", {
//         type: "Phone",
//         mode_of_payment: payment_method,
//         amount: parseFloat(amount_due)
//       });

//       frappe.msgprint("WaafiPay payment requested successfully");
//     } else {
//       frappe.msgprint("Failed to request payment");
//     }
//   }
// });