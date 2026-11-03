// Designer journey (REQUIREMENTS.md section 13, UI end-to-end): upload a broken form, see the
// issues, download the highlighted workbook, upload the fix, preview with live skip logic,
// publish. Then a collector fills the form on Desk and on the web.
const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const FIX = path.join(__dirname, "..", ".fixtures");
const formId = () => fs.readFileSync(path.join(FIX, "form_id.txt"), "utf8").trim();

test.describe.configure({ mode: "serial" });

async function uploadThroughDialog(page, file) {
	const dialog = page.locator(".modal:visible").filter({ hasText: "Upload a workbook" });
	await expect(dialog).toBeVisible();
	await dialog.locator('[data-fieldname="file_url"] button').first().click();
	const uploader = page
		.locator(".modal:visible")
		.filter({ hasText: /Drag and drop|Upload/ })
		.last();
	await uploader.locator('input[type="file"]').first().setInputFiles(file);
	await uploader.getByRole("button", { name: "Upload" }).last().click();
	await expect(dialog.locator('[data-fieldname="file_url"] a.attached-file-link')).toBeVisible({
		timeout: 30_000,
	});
	await dialog.getByRole("button", { name: "Upload and check" }).click();
}

test("designer uploads, fixes, previews and publishes", async ({ page }) => {
	await page.goto("/desk/xlsform");
	await page.getByRole("button", { name: "Upload a workbook" }).click();
	await uploadThroughDialog(page, path.join(FIX, "broken.xlsx"));

	// the version page shows the problem at its cell, in plain language
	await expect(page).toHaveURL(new RegExp(`/(app|desk)/xlsform-version/${formId()}-v1`), {
		timeout: 30_000,
	});
	const report = page.locator(".xf-report");
	await expect(report).toContainText("1 errors");
	await expect(report.locator("a.xf-copy", { hasText: "survey!G5" })).toBeVisible();
	await expect(report).toContainText("${hh_sise}");
	await expect(report).toContainText("Did you mean ${hh_size}?");
	await expect(report).not.toContainText("Traceback");

	// the highlighted workbook downloads (same URL the button opens)
	await expect(
		page.getByRole("button", { name: "Download highlighted workbook" })
	).toBeVisible();
	const annotated = await page.request.get(
		`/api/method/xlsform.api.forms.validation_report?version=${formId()}-v1&format=xlsx`
	);
	expect(annotated.ok()).toBeTruthy();
	expect(annotated.headers()["content-disposition"]).toContain("checked.xlsx");

	// upload the corrected workbook: same version replaces the draft
	await page.getByRole("button", { name: "Upload a corrected workbook" }).click();
	await uploadThroughDialog(page, path.join(FIX, "fixed.xlsx"));
	await expect(page.locator(".xf-report")).not.toContainText("errors", { timeout: 30_000 });
	await expect(page.getByText("No errors.", { exact: false }).first()).toBeVisible();

	// warnings must be accepted before publishing
	await page.getByRole("checkbox", { name: "I understand the warnings" }).check();
	await page.waitForTimeout(800);

	// preview: skip logic runs live
	await page.getByRole("button", { name: "Preview" }).click();
	const preview = page.locator(".modal:visible").filter({ hasText: "Preview:" });
	await expect(preview).toContainText("Do you consent?");
	await expect(preview.locator('.frappe-control[data-fieldname="hh_head"]')).toBeHidden();
	await page.evaluate(() => xlsform.preview_dialog.set_value("consent", "yes"));
	await expect(preview.locator('.frappe-control[data-fieldname="hh_head"]')).toBeVisible();
	await page.evaluate(() => xlsform.preview_dialog.set_value("hh_size", 99));
	await preview.getByRole("button", { name: "Check answers" }).click();
	const result = page
		.locator(".modal:visible")
		.filter({ hasText: "These answers would be refused" });
	await expect(result).toContainText("Between 1 and 39");
	await page.keyboard.press("Escape");
	await page.keyboard.press("Escape");

	// publish
	await page.reload();
	await page.getByRole("button", { name: "Publish" }).click();
	await page.locator(".modal:visible").getByRole("button", { name: "Yes" }).click();
	await expect(page.getByText("Published: this is the version collectors use.")).toBeVisible({
		timeout: 60_000,
	});
});

test("collector fills the form on Desk with live skip logic", async ({ page }) => {
	const dt = await page
		.evaluate(
			async (fid) =>
				(
					await frappe.db.get_value("XLSForm", fid, "data_doctype")
				).message.data_doctype,
			formId()
		)
		.catch(async () => null);
	await page.goto("/desk");
	const doctype = await page.evaluate(
		async (fid) =>
			(
				await frappe.db.get_value("XLSForm", fid, "data_doctype")
			).message.data_doctype,
		formId()
	);
	expect(doctype || dt).toBeTruthy();
	await page.goto(`/desk/${frappe_slug(doctype)}/new`);
	await expect(page.locator('[data-fieldname="consent"]').first()).toBeVisible();
	await expect(page.locator('.frappe-control[data-fieldname="hh_head"]')).toBeHidden();
	await page.evaluate(() => cur_frm.set_value("consent", "yes"));
	await expect(page.locator('.frappe-control[data-fieldname="hh_head"]')).toBeVisible();

	// saving with problems lists every one of them
	await page.evaluate(() =>
		cur_frm.set_value({ hh_head: "Asha", hh_size: 50, district: "d1", village: "v1", ack: 1 })
	);
	await page.evaluate(() => cur_frm.save().catch(() => null));
	const msg = page.locator(".modal:visible .msgprint");
	await expect(msg).toContainText("Between 1 and 39", { timeout: 15_000 });
	const msgDialog = page
		.locator(".modal:visible")
		.filter({ hasText: "Please check these answers" });
	await msgDialog.locator(".btn-modal-close").click();
	await expect(msgDialog).toBeHidden();

	await page.evaluate(() => cur_frm.set_value("hh_size", 2));
	await page.evaluate(() => cur_frm.save());
	await expect(page).toHaveURL(/-\d{5}$/, { timeout: 15_000 }); // saved: the URL now ends in the record name
});

test("collector fills the web form", async ({ page }) => {
	const route = "/xf/" + formId().replace(/_/g, "-") + "/new";
	await page.goto(route);
	await expect(page.locator(".web-form")).toBeVisible();
	await expect(page.locator('.frappe-control[data-fieldname="hh_head"]')).toBeHidden();
	await page.evaluate(() => frappe.web_form.set_value("consent", "yes"));
	await expect(page.locator('.frappe-control[data-fieldname="hh_head"]')).toBeVisible();
});

function frappe_slug(doctype) {
	return doctype.toLowerCase().replace(/ /g, "-");
}
