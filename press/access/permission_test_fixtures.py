"""Synthetic access records, inserted without controllers and always rolled back."""

import frappe
from frappe.utils import now_datetime


def insert(doctype, name, **values):
	values.update(
		name=name,
		creation=now_datetime(),
		modified=now_datetime(),
		owner="Administrator",
		modified_by="Administrator",
		docstatus=0,
		idx=0,
	)
	columns = set(frappe.db.get_table_columns(doctype))
	values = {k: v for k, v in values.items() if k in columns}
	frappe.db.sql(
		"INSERT INTO `tab"
		+ doctype
		+ "` ("
		+ ",".join("`" + k + "`" for k in values)
		+ ") VALUES ("
		+ ",".join(["%s"] * len(values))
		+ ")",
		tuple(values.values()),
	)


def create(relaxed=False):
	personas = ["owner", "admin", "developer", "billing", "restricted", "unassigned", "outsider", "operator"]
	users = {p: "permission-review-" + p + "@example.invalid" for p in personas}
	for persona, user in users.items():
		insert(
			"User",
			user,
			email=user,
			first_name=persona,
			enabled=1,
			user_type="System User" if persona == "operator" else "Website User",
		)
		insert(
			"Has Role",
			"review-user-role-" + persona,
			parent=user,
			parenttype="User",
			parentfield="roles",
			role="Press User" if frappe.db.exists("Role", "Press User") else "Press Member",
		)
	team = "permission-review-team"
	insert("Team", team, user=users["owner"], enabled=1, relaxed_permissions=int(relaxed), country="Pakistan")
	for persona in personas:
		if persona not in ["outsider", "operator"]:
			insert(
				"Team Member",
				"review-member-" + persona,
				parent=team,
				parenttype="Team",
				parentfield="team_members",
				user=users[persona],
				role="Developer",
			)
	for persona, options in [
		("admin", {"admin_access": 1}),
		(
			"developer",
			{
				"all_sites": 1,
				"all_servers": 1,
				"all_release_groups": 1,
				"allow_site_creation": 1,
				"allow_server_creation": 1,
				"allow_bench_creation": 1,
			},
		),
		("billing", {"allow_billing": 1}),
		("restricted", {}),
	]:
		role = "permission-review-role-" + persona
		insert("Press Role", role, team=team, title="Review " + persona, **options)
		insert(
			"Press Role User",
			"review-role-user-" + persona,
			parent=role,
			parenttype="Press Role",
			parentfield="users",
			user=users[persona],
		)
	for doctype in ["Site", "Server", "Release Group"]:
		insert(doctype, "000-permission-review-" + doctype.lower().replace(" ", "-"), team=team)
	return {"users": users, "team": team}
