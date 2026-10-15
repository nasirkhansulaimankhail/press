"""Keep standard document permissions consistent with dashboard resource roles."""

import frappe

from press.guards import role_guard
from press.utils import is_admin_user, is_team_owner
from press.utils.user import is_system_manager

RESOURCE_TYPES = ("Site", "Server", "Release Group")
CREATE_FLAGS = {
	"Site": "allow_site_creation",
	"Server": "allow_server_creation",
	"Release Group": "allow_bench_creation",
}
BILLING_TYPES = ("Invoice", "Balance Transaction", "Stripe Payment Method")


def permits_document(doc, ptype: str) -> bool:
	if doc.doctype in RESOURCE_TYPES:
		if ptype == "create":
			return role_guard.permits_flag(CREATE_FLAGS[doc.doctype])
		return role_guard.permits(doc.doctype, doc.name)
	if doc.doctype in BILLING_TYPES:
		return role_guard.permits_flag("allow_billing")
	return True


def permits_team_management(team: str, user: str | None = None) -> bool:
	if is_system_manager(user):
		return True
	if user and user != frappe.session.user:
		return False
	return is_team_owner(team) or is_admin_user(team)


def query_condition(doctype: str) -> str:
	if doctype in BILLING_TYPES and not role_guard.permits_flag("allow_billing"):
		return "1=0"
	if doctype not in RESOURCE_TYPES or not role_guard.is_restricted():
		return ""
	from press.guards.role_guard.document import has_user_permission

	if has_user_permission(doctype):
		return ""
	names = role_guard.permitted_documents(doctype)
	if not names:
		return "1=0"
	values = ", ".join(frappe.db.escape(name) for name in names)
	return f"`tab{doctype}`.`name` IN ({values})"


def scope_condition(doctype: str, team: str) -> str:
	condition = f"(`tab{doctype}`.`team` = {frappe.db.escape(team)})"
	if restriction := query_condition(doctype):
		condition += f" AND ({restriction})"
	return condition
