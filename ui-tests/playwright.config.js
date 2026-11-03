// Runs against a bench site with xlsform installed. Override with XLSFORM_BASE_URL.
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
	testDir: "./tests",
	timeout: 120_000,
	retries: process.env.CI ? 1 : 0,
	workers: 1,
	reporter: [["list"]],
	globalSetup: require.resolve("./global-setup.js"),
	use: {
		baseURL: process.env.XLSFORM_BASE_URL || "http://xlsform.localhost:8000",
		screenshot: "only-on-failure",
		trace: "retain-on-failure",
		viewport: { width: 1360, height: 900 },
		storageState: ".fixtures/admin.json",
	},
});
