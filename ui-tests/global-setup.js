// Writes the workbooks the tests upload (generated from the same Python fixtures as the
// unit tests) and logs in once as Administrator.
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { request } = require("@playwright/test");

module.exports = async (config) => {
	const out = path.join(__dirname, ".fixtures");
	fs.mkdirSync(out, { recursive: true });
	const python =
		process.env.XLSFORM_PYTHON ||
		path.join(process.env.HOME, "bench/frappe-bench/env/bin/python");
	const formId = "ui_" + Date.now().toString(36);
	execFileSync(python, [path.join(__dirname, "make_fixtures.py"), out, formId], {
		cwd: path.join(__dirname, ".."),
		stdio: "inherit",
	});
	fs.writeFileSync(path.join(out, "form_id.txt"), formId);

	const baseURL = config.projects[0].use.baseURL;
	const ctx = await request.newContext({ baseURL });
	const r = await ctx.post("/api/method/login", {
		data: { usr: "Administrator", pwd: process.env.XLSFORM_ADMIN_PASSWORD || "admin" },
	});
	if (!r.ok()) throw new Error("login failed: " + r.status());
	await ctx.storageState({ path: path.join(out, "admin.json") });
	await ctx.dispose();
};
