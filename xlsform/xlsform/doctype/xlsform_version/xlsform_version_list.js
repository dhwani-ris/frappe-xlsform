frappe.listview_settings["XLSForm Version"] = {
	add_fields: ["state", "docstatus"],
	has_indicator_for_draft: 1,
	get_indicator(doc) {
		const colours = {
			Uploaded: "blue",
			Invalid: "red",
			Valid: "orange",
			Published: "green",
			Superseded: "grey",
		};
		return [__(doc.state), colours[doc.state] || "grey", "state,=," + doc.state];
	},
	onload(list) {
		list.page.add_inner_button(__("Upload a workbook"), () => xlsform.upload_dialog());
	},
};
