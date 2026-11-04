// Copyright (c) 2026, Dhwani RIS and contributors
// For license information, please see LICENSE

frappe.ui.form.on("XLSForm", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Upload new version"),
			() => xlsform.upload_dialog(frm.doc.name),
			null
		);
		frm.change_custom_button_type(__("Upload new version"), null, "primary");

		if (frm.doc.data_doctype) {
			frm.add_custom_button(__("Open records"), () =>
				frappe.set_route("List", frm.doc.data_doctype)
			);
			frm.add_custom_button(
				__("Export Excel"),
				() => xlsform.export(frm.doc.name, "xlsx"),
				__("Data")
			);
			frm.add_custom_button(
				__("Export CSV"),
				() => xlsform.export(frm.doc.name, "csv"),
				__("Data")
			);
			if (frm.doc.allow_web && frm.doc.status === "Published") {
				const route = "/xf/" + frm.doc.form_id.replace(/_/g, "-");
				frm.add_custom_button(
					__("Open web form"),
					() => window.open(route + "/new", "_blank"),
					__("Data")
				);
			}
		}
		if (frm.doc.status === "Published") {
			frm.add_custom_button(__("Retire form"), () => {
				frappe.confirm(
					__(
						"Retire {0}? New records are refused on every channel; existing data, reports and exports stay. Publishing a new version re-opens it.",
						[frappe.utils.escape_html(frm.doc.title)]
					),
					() =>
						frappe
							.call("xlsform.api.forms.retire", { form: frm.doc.name })
							.then(() => frm.reload_doc())
				);
			});
		}
		frm.add_custom_button(__("Versions"), () =>
			frappe.set_route("List", "XLSForm Version", { form: frm.doc.name })
		);
		xlsform.show_status(frm);
	},
});
