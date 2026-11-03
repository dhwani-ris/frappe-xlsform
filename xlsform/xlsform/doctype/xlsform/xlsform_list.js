frappe.listview_settings["XLSForm"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colours = { Draft: "orange", Published: "green", Retired: "grey" };
		return [__(doc.status), colours[doc.status] || "grey", "status,=," + doc.status];
	},
	onload(list) {
		list.page.add_inner_button(__("Upload a workbook"), () => xlsform.upload_dialog());
		list.page.add_inner_button(__("Starter workbook"), () => window.open("/api/method/xlsform.api.forms.template"));
	},
};
