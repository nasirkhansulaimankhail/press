# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import frappe

try:
	import frappe_mcp
except ModuleNotFoundError as exc:
	if exc.name != "frappe_mcp":
		raise
	frappe_mcp = None
from frappe.utils.data import sbool

mcp = frappe_mcp.MCP("press-mcp") if frappe_mcp is not None else None


def _register_handler():
	return mcp.register() if mcp is not None else frappe.whitelist()


@_register_handler()
def handler():
	frappe.only_for("System Manager")

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")

	# Allow unchecked access to System Users
	if user_type != "System User":
		frappe.throw("Access not allowed for this URL", frappe.AuthenticationError)

	# MCP feature flag should be enabled
	if not sbool(str(frappe.get_value("Press Settings", None, "enable_mcp"))):
		frappe.throw("MCP is not enabled", frappe.AuthenticationError)

	if mcp is None:
		frappe.throw("MCP dependencies are not installed for this runtime", frappe.ValidationError)

	import press.mcp.tools.actions
	import press.mcp.tools.codebase
	import press.mcp.tools.documents
	import press.mcp.tools.routes
	import press.mcp.tools.telemetry

	_ = press.mcp.tools.codebase
	_ = press.mcp.tools.documents
	_ = press.mcp.tools.routes
	_ = press.mcp.tools.telemetry
	_ = press.mcp.tools.actions
