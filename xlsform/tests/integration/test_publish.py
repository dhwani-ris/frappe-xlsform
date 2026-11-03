"""End-to-end behaviour on a real site (REQUIREMENTS.md section 13, "Server integration").

Publishing runs DDL, which MariaDB commits implicitly, so every test uses its own form_id
(random suffix) instead of relying on rollback.
"""

import io
import json
import uuid

import frappe
from frappe.tests import IntegrationTestCase
from openpyxl import load_workbook

from xlsform.api import data as data_api
from xlsform.api import forms
from xlsform.runtime import apply as xf_apply
from xlsform.tests.workbooks import HOUSEHOLD, make_xlsx

DESIGNER = "XLSForm Designer"


def uid() -> str:
	return uuid.uuid4().hex[:6]


def household(form_id: str, version: str = "1", survey=None, choices=None, title="Household Survey") -> bytes:
	settings = [["form_title", "form_id", "version", "default_language"], [title, form_id, version, "English (en)"]]
	return make_xlsx(survey=survey or HOUSEHOLD["survey"], choices=choices or HOUSEHOLD["choices"], settings=settings)


def upload(content: bytes, filename="form.xlsx", form=None) -> dict:
	f = frappe.get_doc({"doctype": "File", "file_name": filename, "content": content, "is_private": 1}).insert(
		ignore_permissions=True
	)
	return forms.upload(file_url=f.file_url, form=form)


def publish(content: bytes) -> dict:
	res = upload(content)
	assert res["version"], res
	assert res["state"] == "Valid", [i["message"] for i in res["issues"] if i["severity"] == "error"]
	forms.publish(res["version"], accept_warnings=1)
	status = forms.publish_status(res["version"])
	assert status["published"], status
	return res


def make_user(email: str, roles: list[str]) -> str:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0})
		user.insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for r in roles:
		if not frappe.db.exists("Role", r):
			frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 1}).insert(ignore_permissions=True)
		user.append("roles", {"role": r})
	user.save(ignore_permissions=True)
	return email


GOOD = {
	"consent": "yes",
	"hh_head": "Asha",
	"hh_size": 2,
	"district": "d1",
	"village": "v1",
	"services": [{"choice": "health"}],
	"health_detail": "vaccination",
	"ack": 1,
	"member": [{"m_name": "A", "m_age": 30}, {"m_name": "B", "m_age": 9, "m_school": "yes"}],
}


class TestPublishAndCollect(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_upload_publish_and_collect(self):
		fid = f"hh_{uid()}"
		res = publish(household(fid))
		form = frappe.get_doc("XLSForm", fid)
		self.assertEqual(form.status, "Published")
		dt = form.data_doctype
		meta = frappe.get_meta(dt)
		self.assertEqual(meta.module, "XLSForm Data")
		self.assertTrue(meta.custom)
		self.assertEqual(meta.get_field("services").fieldtype, "Table MultiSelect")
		self.assertEqual(meta.get_field("member").fieldtype, "Table")
		self.assertIn("eval:", meta.get_field("hh_head").depends_on)
		village = meta.get_field("village")
		self.assertIn("eval:cstr(doc.district)", village.link_filters)

		doc = frappe.get_doc({"doctype": dt, **GOOD}).insert()
		self.assertEqual(doc.xf_form, fid)
		self.assertEqual(doc.xf_version, res["version"])
		self.assertEqual(doc.n_members, "2")
		self.assertEqual(doc.total_age, "39")
		self.assertTrue(doc.start)

		# non-relevant answers are cleared, as in ODK
		doc.consent = "no"
		doc.save()
		self.assertFalse(doc.hh_head)
		self.assertEqual(doc.services, [])

	def test_invalid_record_lists_every_problem(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		bad = {**GOOD, "hh_size": 50, "village": "v3", "ack": 0, "member": [{"m_name": "C", "m_age": 200}]}
		with self.assertRaises(frappe.ValidationError) as ctx:
			frappe.get_doc({"doctype": dt, **bad}).insert()
		message = str(ctx.exception)
		self.assertIn("Between 1 and 39", message)  # designer's constraint_message
		self.assertIn("Village", message)  # choice filter
		self.assertIn("I confirm the answers are correct", message)  # required acknowledge
		self.assertIn("row 1", message)  # repeat row
		self.assertNotIn("Traceback", message)

	def test_republish_keeps_old_records_valid(self):
		fid = f"hh_{uid()}"
		publish(household(fid, "1"))
		form = frappe.get_doc("XLSForm", fid)
		old = frappe.get_doc({"doctype": form.data_doctype, **GOOD}).insert()

		survey = [list(r) for r in HOUSEHOLD["survey"]]
		header = survey[0]
		survey = [r for r in survey if r[1] != "health_detail"]  # removed question
		survey.insert(5, ["text", "phone", "Phone number"] + [None] * (len(header) - 3))  # added
		for r in survey:
			if r[1] == "hh_head":
				r[0] = "integer"  # type change: new column
		choices = [*HOUSEHOLD["choices"], ["village", "v4", "Village D", None, "d2"]]
		choices = [c for c in choices if c[1] != "v2"]  # retired choice
		res2 = publish(household(fid, "2", survey=survey, choices=choices))
		self.assertEqual(frappe.db.get_value("XLSForm Version", f"{fid}-v1", "state"), "Superseded")
		form.reload()
		self.assertEqual(form.current_version, res2["version"])

		meta = frappe.get_meta(form.data_doctype)
		self.assertTrue(meta.get_field("health_detail").hidden)  # retired, column kept
		self.assertTrue(meta.get_field("phone"))
		new_head = next(f for f in meta.fields if f.fieldname.startswith("hh_head_v"))
		self.assertEqual(new_head.fieldtype, "Int")
		self.assertEqual(meta.get_field("hh_head").fieldtype, "Small Text")
		lists = json.loads(frappe.db.get_value("XLSForm Version", res2["version"], "compiled_meta"))["doctypes"]["lists"]
		self.assertTrue(frappe.db.get_value(lists["village"], "v2", "xf_retired"))
		self.assertTrue(frappe.db.exists(lists["village"], "v4"))

		old.reload()
		self.assertEqual(old.hh_head, "Asha")  # data never cast or moved
		self.assertEqual(old.health_detail, "vaccination")
		old.save()  # still valid under its own version's rules
		self.assertEqual(old.xf_version, f"{fid}-v1")

	def test_draft_replaced_by_same_version(self):
		fid = f"hh_{uid()}"
		broken = [list(r) for r in HOUSEHOLD["survey"]]
		broken[4][6] = "${nope} > 1"
		first = upload(household(fid, "7", survey=broken))
		self.assertEqual(first["state"], "Invalid")
		self.assertIn("E-REF-UNKNOWN", {i["code"] for i in first["issues"]})
		second = upload(household(fid, "7"))
		self.assertEqual(second["version"], first["version"])
		self.assertEqual(second["state"], "Valid")
		self.assertEqual(frappe.db.count("XLSForm Version", {"form": fid}), 1)

	def test_published_version_cannot_be_reused(self):
		fid = f"hh_{uid()}"
		publish(household(fid, "3"))
		res = upload(household(fid, "3"))
		self.assertIsNone(res["version"])
		self.assertIn("E-VERSION-PUBLISHED", {i["code"] for i in res["issues"]})
		self.assertTrue(res["report_token"])

	def test_retire_and_reopen(self):
		fid = f"hh_{uid()}"
		publish(household(fid, "1"))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		forms.retire(fid)
		with self.assertRaises(frappe.ValidationError) as ctx:
			frappe.get_doc({"doctype": dt, **GOOD}).insert()
		self.assertIn("closed", str(ctx.exception))
		self.assertFalse(frappe.db.get_value("Web Form", {"doc_type": dt}, "published"))
		publish(household(fid, "2"))
		self.assertEqual(frappe.db.get_value("XLSForm", fid, "status"), "Published")
		frappe.get_doc({"doctype": dt, **GOOD}).insert()

	def test_translations_web_form_and_preview(self):
		fid = f"hh_{uid()}"
		res = publish(household(fid))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		self.assertTrue(
			frappe.db.exists("Translation", {"language": "hi", "source_text": "Household size", "context": dt})
		)
		self.assertTrue(frappe.db.exists("Translation", {"language": "hi", "source_text": "Yes"}))
		wf = frappe.get_doc("Web Form", {"doc_type": dt})
		self.assertTrue(wf.login_required)
		self.assertEqual(wf.route, "xf/" + fid.replace("_", "-"))
		types = {f.fieldname: f.fieldtype for f in wf.web_form_fields}
		self.assertEqual(types["services"], "Table")
		self.assertNotIn("xf_form", types)

		preview = forms.preview(res["version"])
		names = {f["fieldname"]: f for f in preview["fields"]}
		self.assertEqual(names["district"]["fieldtype"], "Autocomplete")
		self.assertTrue(names["hh_head"]["depends_on"].startswith("eval:"))
		result = forms.check_answers(res["version"], json.dumps({**GOOD, "hh_size": 99}))
		self.assertFalse(result["ok"])
		self.assertTrue(any("Between 1 and 39" in f["message"] for f in result["failures"]))
		stored = json.loads(frappe.db.get_value("XLSForm Version", res["version"], "test_results"))
		self.assertEqual(len(stored), 1)
		self.assertEqual(frappe.db.count(dt), 0)  # test answers never reach the data table

	def test_export_uses_original_names(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		frappe.get_doc({"doctype": dt, **GOOD}).insert()
		data_api.export(fid, "xlsx")
		wb = load_workbook(io.BytesIO(frappe.response["filecontent"]))
		self.assertEqual(wb.sheetnames, [fid, f"{fid}-member"])
		header = [c.value for c in wb[fid][1]]
		self.assertIn("hh_head", header)
		self.assertIn("services", header)
		row = dict(zip(header, [c.value for c in wb[fid][2]], strict=False))
		self.assertEqual(row["services"], "health")
		self.assertEqual(row["ack"], "OK")
		members = list(wb[f"{fid}-member"].iter_rows(values_only=True))
		self.assertEqual(members[0][:3], ("KEY", "PARENT_KEY", "m_name"))
		self.assertEqual(len(members), 3)

	def test_annotated_workbook(self):
		fid = f"hh_{uid()}"
		broken = [list(r) for r in HOUSEHOLD["survey"]]
		broken[4][6] = "${hh_sise} > 1"
		res = upload(household(fid, "1", survey=broken))
		forms.validation_report(res["version"], format="xlsx")
		wb = load_workbook(io.BytesIO(frappe.response["filecontent"]))
		cell = wb["survey"]["G5"]
		self.assertIn("E-REF-UNKNOWN", cell.comment.text)
		self.assertIn("xlsform_report", wb.sheetnames)

	def test_labels_are_escaped(self):
		fid = f"hh_{uid()}"
		survey = [
			["type", "name", "label", "relevant"],
			["text", "a", "<script>alert(1)</script> Name", None],
			["note", "n", "<img src=x onerror=alert(1)> **Bold**", None],
			["text", "b", "B", "${a} = 'x\" + alert(1) + \"'"],
		]
		publish(make_xlsx(survey=survey, settings=[["form_id", "version"], [fid, "1"]]))
		meta = frappe.get_meta(frappe.db.get_value("XLSForm", fid, "data_doctype"))
		self.assertNotIn("<script>", meta.get_field("a").label)
		self.assertNotIn("<img", meta.get_field("n").options)
		self.assertIn("<strong>Bold</strong>", meta.get_field("n").options)
		self.assertEqual(meta.get_field("b").depends_on, 'eval:(cstr(doc.a) === "x\\" + alert(1) + \\"")')


class TestAccessAndSecurity(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_roles_from_access_table(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		form = frappe.get_doc("XLSForm", fid)
		dt = form.data_doctype
		officer = make_user(f"officer-{uid()}@example.com", ["Field Officer"])
		other = make_user(f"other-{uid()}@example.com", ["Field Officer"])
		stranger = make_user(f"stranger-{uid()}@example.com", ["Blogger"])

		self.assertFalse(frappe.has_permission(dt, "read", user=stranger))
		self.assertFalse(frappe.has_permission(dt, "read", user=officer))  # nothing until granted

		form.append("access", {"role": "Field Officer", "can_read": 1, "can_create": 1, "can_write": 1, "only_own": 1})
		form.save()
		self.assertTrue(frappe.has_permission(dt, "create", user=officer))
		self.assertFalse(frappe.has_permission(dt, "read", user=stranger))

		frappe.set_user(officer)
		mine = frappe.get_doc({"doctype": dt, **GOOD}).insert()
		frappe.set_user(other)
		frappe.get_doc({"doctype": dt, **GOOD}).insert()
		self.assertEqual(frappe.get_list(dt, pluck="name"), [n for n in frappe.get_list(dt, pluck="name")])
		self.assertNotIn(mine.name, frappe.get_list(dt, pluck="name"))  # only own records
		frappe.set_user("Administrator")

		lists = json.loads(frappe.db.get_value("XLSForm Version", form.current_version, "compiled_meta"))["doctypes"]["lists"]
		self.assertTrue(frappe.has_permission(lists["district"], "read", user=officer))

		form.access = []
		form.save()
		self.assertFalse(frappe.has_permission(dt, "read", user=officer))

	def test_blocked_roles(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		form = frappe.get_doc("XLSForm", fid)
		form.append("access", {"role": "All", "can_read": 1})
		with self.assertRaises(frappe.ValidationError):
			form.save()

	def test_non_designer_cannot_upload_or_publish(self):
		fid = f"hh_{uid()}"
		res = upload(household(fid))
		collector = make_user(f"collector-{uid()}@example.com", ["Field Officer"])
		frappe.set_user(collector)
		with self.assertRaises(frappe.PermissionError):
			upload(household(f"hh_{uid()}"))
		with self.assertRaises(frappe.PermissionError):
			forms.publish(res["version"])

	def test_designer_can_publish_without_system_manager(self):
		designer = make_user(f"designer-{uid()}@example.com", [DESIGNER])
		frappe.set_user(designer)
		fid = f"hh_{uid()}"
		publish(household(fid))
		self.assertFalse(frappe.has_permission("DocType", "write", user=designer))
		self.assertFalse(frappe.has_permission("Client Script", "create", user=designer))

	def test_apply_refuses_foreign_doctypes(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		form = frappe.get_doc("XLSForm", fid)
		with self.assertRaises(xf_apply.ApplyRefused):
			xf_apply.guard("ToDo", "XF", form.name)
		other = f"hh_{uid()}"
		publish(household(other, title="Other Survey"))
		other_dt = frappe.db.get_value("XLSForm", other, "data_doctype")
		with self.assertRaises(xf_apply.ApplyRefused):
			xf_apply.guard(other_dt, "XF", form.name)

	def test_standard_submit_is_blocked(self):
		res = upload(household(f"hh_{uid()}"))
		doc = frappe.get_doc("XLSForm Version", res["version"])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_uninstall_refuses_to_delete_data(self):
		from xlsform.runtime.hooks import before_uninstall

		publish(household(f"hh_{uid()}"))
		with self.assertRaises(frappe.ValidationError):
			before_uninstall()
