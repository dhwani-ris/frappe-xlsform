app_name = "xlsform"
app_title = "XLSForm"
app_publisher = "Dhwani RIS"
app_description = "Build data-collection forms in Excel and collect into Frappe DocTypes"
app_email = "deepak.batra@dhwaniris.com"
app_license = "agpl-3.0"
required_apps = ["frappe"]

add_to_apps_screen = [
	{
		"name": "xlsform",
		"logo": "/assets/xlsform/images/logo.svg",
		"title": "XLSForm",
		"route": "/desk/excel-forms",
		"has_permission": "xlsform.api.permission.has_app_permission",
	}
]

app_include_js = "xlsform.bundle.js"
app_include_css = "xlsform.bundle.css"

fixtures = [{"dt": "Role", "filters": [["role_name", "in", ["XLSForm Designer"]]]}]

after_install = "xlsform.runtime.hooks.after_install"
after_migrate = "xlsform.runtime.hooks.after_migrate"
before_uninstall = "xlsform.runtime.hooks.before_uninstall"

doc_events = {
	"*": {
		"validate": "xlsform.runtime.hooks.validate_record",
	}
}

scheduler_events = {
	"daily": ["xlsform.api.data.delete_old_exports"],
}
