"""Compatibility routes for existing Helpdesk templates and API callers.

Install univentures_press_custom before using this integration branch.
Permission checks and query behavior live in that app; do not duplicate them here.
"""

import frappe


@frappe.whitelist()
def get_site_options():
	from univentures_press_custom.api.helpdesk_options import get_site_options as implementation

	return implementation()


@frappe.whitelist()
def get_app_options():
	from univentures_press_custom.api.helpdesk_options import get_app_options as implementation

	return implementation()


@frappe.whitelist()
def get_bench_options():
	from univentures_press_custom.api.helpdesk_options import get_bench_options as implementation

	return implementation()


@frappe.whitelist()
def get_server_options():
	from univentures_press_custom.api.helpdesk_options import get_server_options as implementation

	return implementation()
