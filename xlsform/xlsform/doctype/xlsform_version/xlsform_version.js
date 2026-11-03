// Copyright (c) 2026, Dhwani RIS and contributors
// For license information, please see license.txt

frappe.ui.form.on("XLSForm Version", {
	setup(frm) {
		frappe.realtime.on("xlsform_validated", (data) => {
			if (data.version === frm.doc.name) frm.reload_doc();
		});
		frappe.realtime.on("xlsform_published", (data) => {
			if (data.version === frm.doc.name) frm.reload_doc();
		});
	},

	onload(frm) {
		// Publishing goes through the Publish button, never the standard Submit.
		frm.show_submit_message = () => {};
	},

	refresh(frm) {
		frm.disable_save();
		frm.page.clear_primary_action();
		frm.get_field("report_view").$wrapper.html(frm.doc.report_html || "");
		frm.get_field("change_view").$wrapper.html(frm.doc.change_html || "");
		bind_copy_links(frm);
		show_headline(frm);
		if (frm.is_new()) return;

		if (frm.doc.validation_report) {
			frm.add_custom_button(__("Download highlighted workbook"), () => {
				window.open(
					"/api/method/xlsform.api.forms.validation_report?" +
						new URLSearchParams({ version: frm.doc.name, format: "xlsx" })
				);
			});
		}
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Upload a corrected workbook"), () =>
				xlsform.upload_dialog(frm.doc.form, frm)
			);
		}
		if (frm.doc.preview_json) {
			frm.add_custom_button(__("Preview"), () => open_preview(frm));
		}
		if (frm.doc.docstatus === 0 && frm.doc.state === "Valid") {
			frm.page.set_primary_action(__("Publish"), () => publish(frm));
		}
		if (["queued", "compiling", "migrating"].includes(frm.doc.publish_status)) {
			poll_publish(frm);
		}
		frm.add_custom_button(__("Form"), () => frappe.set_route("Form", "XLSForm", frm.doc.form));
	},

	warnings_accepted(frm) {
		frappe.db
			.set_value(frm.doctype, frm.doc.name, "warnings_accepted", frm.doc.warnings_accepted)
			.then(() => frm.reload_doc());
	},
});

function show_headline(frm) {
	const s = frm.doc.state;
	let text, colour;
	if (s === "Uploaded")
		[text, colour] = [__("Checking the workbook… this page updates when it's done."), "blue"];
	else if (s === "Invalid")
		[text, colour] = [
			__("Fix the errors below in Excel, then upload the corrected workbook."),
			"red",
		];
	else if (s === "Valid" && frm.doc.docstatus === 0)
		[text, colour] = [
			frm.doc.warning_count
				? __(
						"No errors. Read the warnings, tick “I understand the warnings”, preview, then publish."
				  )
				: __("No errors. Preview it, then publish."),
			"green",
		];
	else if (s === "Published")
		[text, colour] = [__("Published: this is the version collectors use."), "green"];
	else if (s === "Superseded")
		[text, colour] = [
			__("Superseded by a newer version. Records collected on it stay valid."),
			"grey",
		];
	if (frm.doc.publish_status === "failed")
		[text, colour] = [
			__("Publishing failed: {0}", [frappe.utils.escape_html(frm.doc.publish_error || "")]),
			"red",
		];
	if (text) frm.dashboard.set_headline_alert(`<div class="indicator ${colour}">${text}</div>`);
}

function bind_copy_links(frm) {
	frm.$wrapper.off("click.xfcopy").on("click.xfcopy", "a.xf-copy", (e) => {
		e.preventDefault();
		frappe.utils.copy_to_clipboard($(e.currentTarget).data("copy"));
	});
}

function publish(frm) {
	const go = () =>
		frappe
			.call({
				method: "xlsform.api.forms.publish",
				args: {
					version: frm.doc.name,
					accept_warnings: frm.doc.warnings_accepted ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Starting…"),
			})
			.then(() => poll_publish(frm));
	const changes = frm.doc.change_html
		? `<p>${__("These changes will be made to the form's data table:")}</p>${
				frm.doc.change_html
		  }`
		: "";
	frappe.confirm(
		`${changes}<p>${__(
			"A published version can't be edited; to change the form later, upload a new version."
		)}</p>`,
		go
	);
}

function poll_publish(frm) {
	const labels = {
		queued: __("Waiting to publish…"),
		compiling: __("Building the form…"),
		migrating: __("Creating the data tables…"),
	};
	const tick = () =>
		frappe
			.call({ method: "xlsform.api.forms.publish_status", args: { version: frm.doc.name } })
			.then((r) => {
				const st = r.message;
				if (st.published || st.status === "done") {
					frappe.hide_progress();
					frappe.show_alert({ message: __("Published"), indicator: "green" });
					frm.reload_doc();
				} else if (st.status === "failed") {
					frappe.hide_progress();
					frm.reload_doc();
				} else {
					const step = { queued: 1, compiling: 2, migrating: 3 }[st.status] || 1;
					frappe.show_progress(__("Publishing"), step, 4, labels[st.status] || "");
					setTimeout(tick, 1500);
				}
			});
	tick();
}

function open_preview(frm) {
	frappe
		.call({ method: "xlsform.api.forms.preview", args: { version: frm.doc.name } })
		.then((r) => {
			const p = r.message;
			const note =
				`<div class="xf-preview-note">${__(
					"This is how collectors will see the form. Skip logic works as you type. Use “Check answers” to run the constraints, calculations and other checks done on save."
				)}` +
				(p.truncated_lists && p.truncated_lists.length
					? " " + __("Long choice lists show their first 1,000 choices here.")
					: "") +
				"</div>";
			const d = new frappe.ui.Dialog({
				title: __("Preview: {0}", [frappe.utils.escape_html(p.title || "")]),
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "note", options: note }, ...p.fields],
				primary_action_label: __("Check answers"),
				primary_action() {},
			});
			d.show();
			xlsform.preview_dialog = d;
			// Send whatever is filled in: the server reports missing answers together with every
			// other problem, instead of the dialog stopping at the first required field.
			d.get_primary_btn()
				.off("click")
				.on("click", () => {
					frappe
						.call({
							method: "xlsform.api.forms.check_answers",
							args: {
								version: frm.doc.name,
								values: JSON.stringify(d.get_values(true) || {}),
							},
						})
						.then((res) => show_check_result(res.message));
				});
		});
}

function show_check_result(res) {
	if (res.ok) {
		const calc = Object.entries(res.calculated || {})
			.map(
				([k, v]) =>
					`<li><code>${frappe.utils.escape_html(k)}</code> = ${frappe.utils.escape_html(
						String(v)
					)}</li>`
			)
			.join("");
		frappe.msgprint({
			title: __("All answers pass"),
			indicator: "green",
			message: calc
				? `<p>${__("Calculated values:")}</p><ul>${calc}</ul>`
				: __("No problems found."),
		});
		return;
	}
	const items = res.failures
		.map((f) => {
			const where = f.repeat
				? `${frappe.utils.escape_html(f.repeat)}, ${__("row")} ${f.row + 1}: `
				: "";
			return `<li>${where}${frappe.utils.escape_html(f.message)}</li>`;
		})
		.join("");
	frappe.msgprint({
		title: __("These answers would be refused"),
		indicator: "orange",
		message: `<ul class="xf-preview-failures">${items}</ul>`,
	});
}
