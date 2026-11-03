(() => {
  // ../../../../../../workspace/xlsform/xlsform/public/js/xlsform.bundle.js
  window.xlsform = window.xlsform || {};
  xlsform.show_status = function(frm) {
    const colour = { Draft: "orange", Published: "green", Retired: "grey" }[frm.doc.status] || "blue";
    const msg = {
      Draft: __(
        "Not published yet. Upload a workbook, fix any problems, preview it, then publish."
      ),
      Published: __("Published. Collectors can fill it on Desk, the web and mForm."),
      Retired: __("Retired. New records are refused; publish a new version to re-open it.")
    }[frm.doc.status];
    if (msg)
      frm.dashboard.set_headline_alert(`<div class="indicator ${colour}">${msg}</div>`);
  };
  xlsform.export = function(form, format) {
    window.open(
      "/api/method/xlsform.api.data.export?" + new URLSearchParams({ form, format }).toString(),
      "_blank"
    );
  };
  xlsform.upload_dialog = function(form, frm) {
    const d = new frappe.ui.Dialog({
      title: __("Upload a workbook"),
      fields: [
        {
          fieldtype: "HTML",
          options: `<p class="text-muted">${__(
            "Upload the .xlsx you edited in Excel. Every problem is listed with the sheet, row and cell, and you can download your workbook with the problems highlighted."
          )} <a href="/api/method/xlsform.api.forms.template">${__(
            "Download the starter workbook"
          )}</a></p>`
        },
        {
          fieldtype: "Attach",
          fieldname: "file_url",
          label: __("Workbook (.xlsx)"),
          reqd: 1,
          options: { restrictions: { allowed_file_types: [".xlsx"] } }
        },
        {
          fieldtype: "Attach",
          fieldname: "csv_url",
          label: __("Choice list CSV (only for select_one_from_file)"),
          options: { restrictions: { allowed_file_types: [".csv"] } }
        }
      ],
      primary_action_label: __("Upload and check"),
      primary_action(values) {
        d.disable_primary_action();
        frappe.call({
          method: "xlsform.api.forms.upload",
          args: {
            file_url: values.file_url,
            form: form || void 0,
            csv_urls: values.csv_url ? JSON.stringify([values.csv_url]) : void 0
          },
          freeze: true,
          freeze_message: __("Checking the workbook\u2026")
        }).then((r) => {
          d.hide();
          const res = r.message;
          if (res.version) {
            if (frm && frm.doctype === "XLSForm Version" && frm.doc.name === res.version) {
              frm.reload_doc();
            } else {
              frappe.model.remove_from_locals("XLSForm Version", res.version);
              frappe.set_route("Form", "XLSForm Version", res.version);
            }
          } else {
            xlsform.show_transient(res);
          }
        }).finally(() => d.enable_primary_action());
      }
    });
    d.show();
  };
  xlsform.show_transient = function(res) {
    const rows = (res.issues || []).map(
      (i) => `<tr><td class="text-nowrap">${frappe.utils.escape_html(
        i.cell ? i.sheet + "!" + i.cell : i.sheet || ""
      )}</td>
			<td>${frappe.utils.escape_html(i.message)}</td><td>${frappe.utils.escape_html(
        i.suggestion
      )}</td></tr>`
    ).join("");
    const d = new frappe.ui.Dialog({
      title: __("This workbook can't be used yet"),
      size: "extra-large",
      fields: [
        {
          fieldtype: "HTML",
          options: `<table class="table table-bordered"><thead><tr><th>${__(
            "Cell"
          )}</th><th>${__("Problem")}</th><th>${__(
            "Suggested fix"
          )}</th></tr></thead><tbody>${rows}</tbody></table>`
        }
      ],
      primary_action_label: __("Download highlighted workbook"),
      primary_action() {
        window.open(
          "/api/method/xlsform.api.forms.validation_report?" + new URLSearchParams({ token: res.report_token, format: "xlsx" })
        );
      }
    });
    d.show();
  };
})();
//# sourceMappingURL=xlsform.bundle.US7P3Q5T.js.map
