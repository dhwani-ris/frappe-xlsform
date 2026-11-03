"""Regression tests for the security and robustness findings of the November 2026 review."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from xlsform.api import data as data_api
from xlsform.api import forms
from xlsform.runtime import access, hooks
from xlsform.tests.integration.test_publish import DESIGNER, GOOD, household, make_user, publish, uid, upload
from xlsform.tests.workbooks import make_xlsx


def private_file(name: str, content: bytes) -> str:
	frappe.set_user("Administrator")
	return (
		frappe.get_doc({"doctype": "File", "file_name": name, "content": content, "is_private": 1})
		.insert(ignore_permissions=True)
		.file_url
	)


def simple_form(form_id: str, version: str = "1") -> bytes:
	return make_xlsx(
		survey=[["type", "name", "label"], ["text", "hh_head", "Head"], ["integer", "hh_size", "Size"]],
		settings=[["form_id", "version"], [form_id, version]],
	)


class TestFileAccess(IntegrationTestCase):
	def setUp(self):
		self.designer = make_user(f"designer-{uid()}@example.com", [DESIGNER])

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_upload_refuses_a_csv_the_designer_cannot_read(self):
		secret = private_file(f"secret-{uid()}.csv", b"salary,pan\n1,ABCDE1234F\n")
		frappe.set_user(self.designer)
		with self.assertRaises(frappe.PermissionError):
			upload(household(f"hh_{uid()}"), form=None, csv_urls=json.dumps([secret]))

	def test_upload_refuses_a_workbook_the_designer_cannot_read(self):
		secret = private_file(f"secret-{uid()}.xlsx", household(f"hh_{uid()}"))
		frappe.set_user(self.designer)
		with self.assertRaises(frappe.PermissionError):
			forms.upload(file_url=secret)

	def test_designer_cannot_change_system_fields_of_a_version(self):
		frappe.set_user(self.designer)
		res = upload(household(f"hh_{uid()}"))
		secret = private_file(f"secret-{uid()}.xlsx", household(f"hh_{uid()}"))
		frappe.set_user(self.designer)
		doc = frappe.get_doc("XLSForm Version", res["version"])
		before = {
			f: doc.get(f) for f in ("source_file", "report_html", "preview_json", "compiled_meta", "state")
		}
		doc.update(
			{
				"source_file": secret,
				"report_html": "<b>x</b>",
				"preview_json": json.dumps({"fields": [{"fieldtype": "HTML", "options": "<img onerror=x>"}]}),
				"compiled_meta": "{}",
				"state": "Valid",
			}
		)
		doc.save()
		doc.reload()
		self.assertEqual({f: doc.get(f) for f in before}, before)

	def test_designer_cannot_change_system_fields_of_a_form(self):
		fid = f"hh_{uid()}"
		frappe.set_user(self.designer)
		publish(household(fid))
		doc = frappe.get_doc("XLSForm", fid)
		before = {f: doc.get(f) for f in ("status", "generated_doctypes", "data_doctype", "current_version")}
		doc.update({"status": "Retired", "generated_doctypes": '["ToDo"]', "data_doctype": "User"})
		doc.save()
		doc.reload()
		self.assertEqual({f: doc.get(f) for f in before}, before)


class TestRecordIntegrity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.form_a = f"hh_{uid()}"
		publish(household(cls.form_a, title=f"Household {cls.form_a}"))
		cls.dt_a = frappe.db.get_value("XLSForm", cls.form_a, "data_doctype")
		cls.form_b = f"sm_{uid()}"
		publish(simple_form(cls.form_b))
		cls.version_b = frappe.db.get_value("XLSForm", cls.form_b, "current_version")

	def setUp(self):
		frappe.set_user("Administrator")

	def test_form_comes_from_the_doctype_not_the_client(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": self.dt_a, **GOOD, "hh_size": 500, "xf_form": self.form_b}).insert()

	def test_version_of_another_form_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": self.dt_a, **GOOD, "hh_size": 500, "xf_version": self.version_b}
			).insert()

	def test_unpublished_version_is_refused(self):
		draft = upload(household(self.form_a, version="99"))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": self.dt_a, **GOOD, "xf_version": draft["version"]}).insert()

	def test_record_keeps_its_published_version(self):
		doc = frappe.get_doc({"doctype": self.dt_a, **GOOD}).insert()
		self.assertEqual(doc.xf_form, self.form_a)
		self.assertEqual(doc.xf_version, frappe.db.get_value("XLSForm", self.form_a, "current_version"))

	def test_version_cannot_change_after_insert(self):
		doc = frappe.get_doc({"doctype": self.dt_a, **GOOD}).insert()
		doc.xf_version = self.version_b
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_channel_is_set_by_the_server(self):
		doc = frappe.get_doc({"doctype": self.dt_a, **GOOD, "xf_channel": "Web"}).insert()
		self.assertEqual(doc.xf_channel, "API")

	def test_retired_form_cannot_be_bypassed(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		forms.retire(fid)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": dt, **GOOD, "xf_form": self.form_b}).insert()


class TestAccessModel(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_designer_sees_data_only_when_granted(self):
		designer = make_user(f"designer-{uid()}@example.com", [DESIGNER])
		frappe.set_user(designer)
		fid = f"hh_{uid()}"
		publish(household(fid))
		frappe.set_user("Administrator")
		form = frappe.get_doc("XLSForm", fid)
		self.assertFalse(frappe.has_permission(form.data_doctype, "read", user=designer))
		form.append("access", {"role": DESIGNER, "can_read": 1, "can_export": 1})
		form.save()
		self.assertTrue(frappe.has_permission(form.data_doctype, "export", user=designer))

	def test_access_table_wins_over_role_permission_manager(self):
		from frappe.permissions import add_permission

		fid = f"hh_{uid()}"
		publish(household(fid))
		form = frappe.get_doc("XLSForm", fid)
		officer = make_user(f"officer-{uid()}@example.com", ["Field Officer"])
		make_user(f"reviewer-{uid()}@example.com", ["xf Reviewer"])
		add_permission(form.data_doctype, "xf Reviewer")
		form.append("access", {"role": "Field Officer", "can_read": 1})
		form.save()
		self.assertTrue(frappe.has_permission(form.data_doctype, "read", user=officer))
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": form.data_doctype}))

	def test_title_change_does_not_resync_access(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		make_user(f"officer-{uid()}@example.com", ["Field Officer"])
		form = frappe.get_doc("XLSForm", fid)
		form.append("access", {"role": "Field Officer", "can_read": 1})
		form.save()
		with patch.object(access, "sync") as sync:
			form.reload()
			form.title = f"Renamed {fid}"
			form.save()
		sync.assert_not_called()


class TestLifecycle(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("XLSForm Settings", "designers_can_publish", 1)

	def test_migrate_keeps_admin_settings(self):
		frappe.db.set_single_value("XLSForm Settings", "designers_can_publish", 0)
		frappe.clear_document_cache("XLSForm Settings", "XLSForm Settings")
		hooks.after_migrate()
		self.assertEqual(frappe.db.get_single_value("XLSForm Settings", "designers_can_publish"), 0)

	def test_workspace_is_built_when_a_designer_publishes(self):
		designer = make_user(f"designer-{uid()}@example.com", [DESIGNER])
		frappe.set_user(designer)
		fid = f"hh_{uid()}"
		publish(household(fid, title=f"Findable {fid}"))
		frappe.set_user("Administrator")
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		ws = frappe.get_doc("Workspace", "Form Data")
		self.assertIn(dt, [s.link_to for s in ws.shortcuts])

	def test_removing_generated_doctypes_drops_their_tables(self):
		from xlsform.runtime.hooks import remove_generated_doctypes

		fid = f"hh_{uid()}"
		publish(household(fid))
		owned = json.loads(frappe.db.get_value("XLSForm", fid, "generated_doctypes"))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		frappe.get_doc({"doctype": dt, **GOOD}).insert()
		remove_generated_doctypes(owned)
		for name in owned:
			self.assertFalse(frappe.db.exists("DocType", name))
			self.assertFalse(frappe.db.table_exists(name))

	def test_failed_background_validation_is_reported(self):
		from xlsform.xlsform.doctype.xlsform_version.xlsform_version import validate_in_background

		res = upload(household(f"hh_{uid()}"))
		with patch("xlsform.runtime.validation.run_for_version", side_effect=RuntimeError("boom")):
			validate_in_background(res["version"])
		state, error = frappe.db.get_value("XLSForm Version", res["version"], ["state", "publish_error"])
		self.assertEqual(state, "Invalid")
		self.assertTrue(error)

	def test_check_answers_leaves_published_version_untouched(self):
		res = publish(household(f"hh_{uid()}"))
		before = frappe.db.get_value("XLSForm Version", res["version"], "modified")
		forms.check_answers(res["version"], json.dumps(GOOD))
		self.assertEqual(frappe.db.get_value("XLSForm Version", res["version"], "modified"), before)

	def test_publish_status_of_unknown_version(self):
		with self.assertRaises(frappe.DoesNotExistError):
			forms.publish_status("no-such-version")


class TestExport(IntegrationTestCase):
	def test_export_is_logged(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		frappe.get_doc({"doctype": dt, **GOOD}).insert()
		data_api.export(fid, "xlsx")
		self.assertTrue(frappe.db.exists("Access Log", {"reference_document": fid, "export_from": dt}))

	def test_large_export_runs_in_background(self):
		fid = f"hh_{uid()}"
		publish(household(fid))
		dt = frappe.db.get_value("XLSForm", fid, "data_doctype")
		for _ in range(3):
			frappe.get_doc({"doctype": dt, **GOOD}).insert()
		with patch.object(data_api, "SYNC_LIMIT", 2):
			result = data_api.export(fid, "xlsx")
		self.assertTrue(result["queued"])
		files = frappe.get_all(
			"File", filters={"attached_to_doctype": "XLSForm", "attached_to_name": fid}, pluck="file_name"
		)
		self.assertTrue(any(f.endswith(".xlsx") for f in files))
