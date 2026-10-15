import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import frappe
import frappe.utils
from frappe.utils import update_progress_bar

if TYPE_CHECKING:
	from frappe.core.doctype.role.role import Role


def execute():
	HasRole = frappe.qb.DocType("Has Role")
	preserve_original_roles()
	users = eligible_users()

	total = len(users)
	chunk_size = 100
	old_roles = ("Press Admin", "Press Member")

	# Give "Press User" role to users who don't have it.
	print(f"Updating {total} users")
	for chunk_start in range(0, total, chunk_size):
		chunk = users[chunk_start : chunk_start + chunk_size]
		now_str = frappe.utils.now()
		query = frappe.qb.into(HasRole).columns(
			"name",
			"creation",
			"modified",
			"modified_by",
			"owner",
			"parent",
			"parentfield",
			"parenttype",
			"role",
		)
		for i, user in enumerate(chunk, start=chunk_start):
			name = frappe.generate_hash(length=10)
			query = query.insert(
				name,
				now_str,
				now_str,
				"Administrator",
				"Administrator",
				user,
				"roles",
				"User",
				"Press User",
			)
			update_progress_bar("Updating users", i, total)
		query.run()
		frappe.db.commit()

	# Remove old roles from all users.
	frappe.qb.from_(HasRole).where(HasRole.role.isin(old_roles)).where(
		HasRole.parenttype == "User"
	).delete().run()

	# Change all remaining "Press Admin" and "Press Member" roles to "Press User".
	frappe.qb.update(HasRole).set(HasRole.role, "Press User").where(HasRole.role.isin(old_roles)).run()

	# Disable old roles.
	for old_role in old_roles:
		if frappe.db.exists("Role", old_role):
			role_doc: Role = frappe.get_doc("Role", old_role)
			role_doc.disabled = True
			role_doc.save()

	frappe.clear_cache()
	# Commit changes.
	frappe.db.commit()


def eligible_users() -> list[str]:
	"""Retain hosting access without promoting unrelated Desk or portal users."""
	existing = set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "role": ["in", ["Press Admin", "Press Member"]]},
			pluck="parent",
		)
	)
	teams = frappe.get_all("Team", filters={"enabled": 1}, fields=["name", "user"])
	members = (
		set(
			frappe.get_all(
				"Team Member",
				filters={"parent": ["in", [team.name for team in teams]], "parenttype": "Team"},
				pluck="user",
			)
		)
		if teams
		else set()
	)
	enabled = set(frappe.get_all("User", filters={"enabled": 1}, pluck="name"))
	eligible = existing | ((members | {team.user for team in teams}) & enabled)
	assigned = set(
		frappe.get_all("Has Role", filters={"parenttype": "User", "role": "Press User"}, pluck="parent")
	)
	return sorted(eligible - assigned - {"Administrator", "Guest", None, ""})


def preserve_original_roles():
	"""Write the original assignments once, before any migration commits."""
	path = Path(frappe.get_site_path("private", "press-role-migration-original.json"))
	path.parent.mkdir(parents=True, exist_ok=True)
	if path.exists():
		return
	data = {
		"site": frappe.local.site,
		"database": frappe.conf.db_name,
		"roles": frappe.get_all("Has Role", fields=["*"]),
		"legacy_role_states": frappe.get_all(
			"Role", filters={"name": ["in", ["Press Admin", "Press Member"]]}, fields=["name", "disabled"]
		),
	}
	with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
		json.dump(data, output, default=str)
		output.flush()
		os.fsync(output.fileno())
