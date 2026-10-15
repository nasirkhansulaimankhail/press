"""Run only on an explicitly authorized isolated site; all inserts roll back."""

import unittest

import frappe
from frappe.client import get as standard_get

from press.access.permission_test_fixtures import create, insert
from press.access.resource_permissions import permits_document
from press.api.client import check_document_write_access, get_list
from press.api.site import protected
from press.guards import role_guard
from press.overrides import before_request
from press.patches.v0_8_0.merge_press_admin_member_roles import eligible_users
from press.utils import _system_user
from press.utils.user import is_desk_user, is_system_manager

RESOURCE_TYPES = ("Site", "Server", "Release Group")


class TestResourcePermissions(unittest.TestCase):
	def setUp(self):
		self.fixture = create()
		frappe.clear_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache()

	def as_persona(self, persona):
		frappe.set_user(self.fixture["users"][persona])
		frappe.session.data.user_type = "System User" if persona == "operator" else "Website User"
		frappe.local.request = frappe._dict(
			method="POST",
			path="/api/method/press.api.client.get_list",
			headers={"X-Press-Team": self.fixture["team"]},
		)
		before_request()

	def name(self, doctype):
		return "000-permission-review-" + doctype.lower().replace(" ", "-")

	def test_standard_and_dashboard_reads_and_writes_agree_for_strict_roles(self):
		for persona in ("owner", "admin", "developer", "billing", "restricted", "unassigned"):
			self.as_persona(persona)
			for doctype in RESOURCE_TYPES:
				with self.subTest(persona=persona, doctype=doctype):
					name = self.name(doctype)
					allowed = persona in ("owner", "admin", "developer")
					doc = frappe.get_doc(doctype, name)
					self.assertEqual(bool(frappe.has_permission(doctype, "write", doc=doc)), allowed)
					endpoint = protected(doctype)(lambda name: "allowed")
					if allowed:
						self.assertEqual(standard_get(doctype, name)["name"], name)
						self.assertEqual(endpoint(name=name), "allowed")
						check_document_write_access(doctype, name)
					else:
						self.assertFalse(frappe.has_permission(doctype, "read", doc=doc))
						with self.assertRaises(frappe.PermissionError):
							standard_get(doctype, name)
						with self.assertRaisesRegex(frappe.PermissionError, "Not Permitted"):
							endpoint(name=name)
						with self.assertRaisesRegex(frappe.PermissionError, "Not permitted"):
							check_document_write_access(doctype, name)

	def test_standard_and_dashboard_lists_hide_ungranted_resources(self):
		for persona in ("owner", "developer", "billing", "restricted", "unassigned"):
			self.as_persona(persona)
			for doctype in RESOURCE_TYPES:
				allowed = persona in ("owner", "developer")
				for rows in (get_list(doctype, fields=["name"]), frappe.get_list(doctype, fields=["name"])):
					self.assertEqual(any(row.name == self.name(doctype) for row in rows), allowed)

	def test_relaxed_unassigned_member_sees_the_resources_they_can_access(self):
		frappe.db.set_value("Team", self.fixture["team"], "relaxed_permissions", 1)
		self.as_persona("unassigned")
		for doctype in RESOURCE_TYPES:
			name = self.name(doctype)
			self.assertEqual(standard_get(doctype, name)["name"], name)
			self.assertIn(name, [row.name for row in get_list(doctype, fields=["name"])])
			self.assertIn(name, frappe.get_list(doctype, pluck="name"))
		self.as_persona("restricted")
		self.assertFalse(role_guard.permits("Site", self.name("Site")))

	def test_desk_user_without_manager_role_does_not_gain_infrastructure_authority(self):
		self.as_persona("operator")
		self.assertTrue(is_desk_user())
		self.assertFalse(is_system_manager())
		self.assertFalse(_system_user())
		from press.utils import get_current_team

		with self.assertRaisesRegex(frappe.AuthenticationError, "not part of any team"):
			get_current_team()

	def test_explicit_system_manager_retains_operator_access(self):
		user = self.fixture["users"]["operator"]
		insert(
			"Has Role",
			"review-manager-role",
			parent=user,
			parenttype="User",
			parentfield="roles",
			role="System Manager",
		)
		frappe.clear_cache()
		self.as_persona("operator")
		self.assertTrue(is_system_manager())
		self.assertTrue(_system_user())
		for doctype in RESOURCE_TYPES:
			name = self.name(doctype)
			self.assertEqual(standard_get(doctype, name)["name"], name)
			self.assertEqual(protected(doctype)(lambda name: "allowed")(name=name), "allowed")

	def test_only_team_administrators_can_modify_membership_and_resource_roles(self):
		role = frappe.get_doc("Press Role", "permission-review-role-admin")
		team = frappe.get_doc("Team", self.fixture["team"])
		for persona in ("owner", "admin", "developer", "billing", "restricted", "unassigned"):
			self.as_persona(persona)
			for doc in (role, team):
				self.assertEqual(
					bool(frappe.has_permission(doc.doctype, "write", doc=doc)),
					persona in ("owner", "admin"),
					(persona, doc.doctype),
				)

	def test_creation_requires_the_matching_resource_flag_and_own_team(self):
		from press.overrides import has_permission

		for persona in ("developer", "billing", "restricted", "unassigned"):
			self.as_persona(persona)
			for doctype in RESOURCE_TYPES:
				doc = frappe.new_doc(doctype)
				doc.team = self.fixture["team"]
				self.assertEqual(permits_document(doc, "create"), persona == "developer")
				self.assertEqual(bool(frappe.has_permission(doctype, "create", doc=doc)), persona == "developer")
				doc.team = "unrelated-permission-review-team"
				self.assertFalse(has_permission(doc, "create", frappe.session.user))

	def test_migration_only_adds_hosting_roles_for_existing_or_enabled_team_users(self):
		users = self.fixture["users"]
		frappe.db.delete("Has Role", {"parent": ["in", list(users.values())]})
		insert(
			"Has Role",
			"review-legacy-role",
			parent=users["outsider"],
			parenttype="User",
			parentfield="roles",
			role="Press Member",
		)
		candidates = set(eligible_users())
		self.assertIn(users["owner"], candidates)
		self.assertIn(users["developer"], candidates)
		self.assertIn(users["outsider"], candidates)
		self.assertNotIn(users["operator"], candidates)
		frappe.db.set_value("User", users["developer"], "enabled", 0)
		self.assertNotIn(users["developer"], eligible_users())
		insert(
			"Has Role",
			"review-already-assigned",
			parent=users["owner"],
			parenttype="User",
			parentfield="roles",
			role="Press User",
		)
		self.assertNotIn(users["owner"], eligible_users())

	def test_billing_document_permissions_match_the_explicit_billing_grant(self):
		for doctype in ("Invoice", "Balance Transaction"):
			name = "permission-review-" + doctype.lower().replace(" ", "-")
			insert(doctype, name, team=self.fixture["team"])
			for persona in ("owner", "admin", "billing", "developer", "restricted"):
				self.as_persona(persona)
				doc = frappe.get_doc(doctype, name)
				allowed = persona in ("owner", "admin", "billing")
				self.assertEqual(bool(frappe.has_permission(doctype, "read", doc=doc)), allowed)
				self.assertEqual(bool(frappe.has_permission(doctype, "write", doc=doc)), allowed)
				self.assertEqual(name in frappe.get_list(doctype, pluck="name"), allowed)

	def test_specific_resource_grants_do_not_allow_other_resource_types(self):
		insert(
			"Press Role Resource",
			"review-specific-resource",
			parent="permission-review-role-restricted",
			parenttype="Press Role",
			parentfield="resources",
			document_type="Site",
			document_name=self.name("Site"),
		)
		self.as_persona("restricted")
		self.assertEqual(standard_get("Site", self.name("Site"))["name"], self.name("Site"))
		self.assertIn(self.name("Site"), frappe.get_list("Site", pluck="name"))
		self.assertFalse(
			frappe.has_permission("Server", "read", doc=frappe.get_doc("Server", self.name("Server")))
		)

	def test_parent_owner_retains_child_team_access_and_cannot_read_unrelated_teams(self):
		insert(
			"Team",
			"permission-review-child",
			parent_team=self.fixture["team"],
			user=self.fixture["users"]["owner"],
			enabled=1,
		)
		insert("Site", "permission-review-child-site", team="permission-review-child")
		insert("Site", "permission-review-foreign-site", team="permission-review-foreign-team")
		self.as_persona("owner")
		self.assertEqual(
			standard_get("Site", "permission-review-child-site")["name"], "permission-review-child-site"
		)
		self.assertFalse(
			frappe.has_permission(
				"Site", "read", doc=frappe.get_doc("Site", "permission-review-foreign-site")
			)
		)
		with self.assertRaises(frappe.PermissionError):
			standard_get("Site", "permission-review-foreign-site")

	def test_support_resource_grant_preserves_scoped_read_without_operator_authority(self):
		from frappe.utils import add_to_date

		user = self.fixture["users"]["operator"]
		insert(
			"Team Member",
			"review-support-member",
			parent=self.fixture["team"],
			parenttype="Team",
			parentfield="team_members",
			user=user,
		)
		insert(
			"Has Role",
			"review-support-role",
			parent=user,
			parenttype="User",
			parentfield="roles",
			role="Press Support Agent",
		)
		insert("Site", "permission-review-support-site", team="permission-review-foreign-team")
		insert(
			"Support Access",
			"permission-review-support-access",
			status="Accepted",
			requested_team=self.fixture["team"],
			target_team="permission-review-foreign-team",
			access_allowed_till=add_to_date(None, hours=1),
		)
		insert(
			"Support Access Resource",
			"review-support-resource",
			parent="permission-review-support-access",
			parenttype="Support Access",
			parentfield="resources",
			document_type="Site",
			document_name="permission-review-support-site",
		)
		self.as_persona("operator")
		self.assertFalse(is_system_manager())
		self.assertEqual(
			standard_get("Site", "permission-review-support-site")["name"], "permission-review-support-site"
		)
		self.assertEqual(
			protected("Site")(lambda name: "allowed")(name="permission-review-support-site"), "allowed"
		)
