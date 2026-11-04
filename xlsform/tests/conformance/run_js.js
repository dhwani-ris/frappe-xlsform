const fs = require("fs");
const path = require("path");
const vm = require("vm");

const [frappeApp, casesPath] = process.argv.slice(2);
const utils = path.join(frappeApp, "frappe/public/js/frappe/utils");

globalThis.window = globalThis;
globalThis.frappe = {
	boot: { sysdefaults: { number_format: "#,###.##" } },
	defaults: { get_default: () => null, is_enabled: () => false },
	model: { get_value: () => null },
};

const common = fs.readFileSync(path.join(utils, "common.js"), "utf8");
const lstrip = common.match(/window\.lstrip = function lstrip[\s\S]*?\n};/);
if (!lstrip) throw new Error("lstrip not found in common.js");
vm.runInThisContext(lstrip[0]);
vm.runInThisContext(fs.readFileSync(path.join(utils, "datatype.js"), "utf8"));
const numberFormat = fs
	.readFileSync(path.join(utils, "number_format.js"), "utf8")
	.replace(/^import .*$/gm, "")
	.replace(/^export /gm, "");
vm.runInThisContext(numberFormat);

const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = cases.map((c) => {
	try {
		const fn = new Function("doc", "parent", `let out = ${c.js}; return out`);
		const doc = c.doc;
		const parent = c.parent || doc;
		const value = fn(doc, parent);
		return { id: c.id, result: c.value ? (value == null ? "" : String(value)) : !!value };
	} catch (e) {
		return { id: c.id, error: String(e) };
	}
});
process.stdout.write(JSON.stringify(out));
