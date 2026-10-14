from __future__ import annotations

import frappe

from press.press.doctype.team.team import get_child_team_members
from press.utils import get_current_team


def _option(label: str | None, value: str | None, description: str | None = None):
	if not value:
		return None

	item = {
		"label": label or value,
		"value": value,
	}
	if description:
		item["description"] = description
	return item


def _team_names() -> list[str]:
	try:
		team = get_current_team()
	except Exception:
		return []

	if not team:
		return []

	child_teams = [row.name for row in get_child_team_members(team)]
	return [team, *child_teams]


def _active_site_names(teams: list[str]) -> list[str]:
	if not teams:
		return []

	return frappe.get_all(
		"Site",
		filters={
			"team": ("in", teams),
			"status": ("!=", "Archived"),
		},
		pluck="name",
		order_by="modified desc",
		limit_page_length=500,
	)


@frappe.whitelist()
def get_site_options():
	teams = _team_names()
	if not teams:
		return []

	sites = frappe.get_all(
		"Site",
		filters={
			"team": ("in", teams),
			"status": ("!=", "Archived"),
		},
		fields=["name", "host_name", "status"],
		order_by="modified desc",
		limit_page_length=500,
	)

	return [
		item
		for item in (
			_option(
				site.host_name or site.name,
				site.name,
				site.status,
			)
			for site in sites
		)
		if item
	]


@frappe.whitelist()
def get_app_options():
	site_names = _active_site_names(_team_names())
	if not site_names:
		return []

	app_names = frappe.get_all(
		"Site App",
		filters={
			"parent": ("in", site_names),
			"parenttype": "Site",
		},
		pluck="app",
		distinct=True,
		order_by="app asc",
		limit_page_length=500,
	)

	app_titles = dict(
		frappe.get_all(
			"App",
			filters={"name": ("in", app_names)},
			fields=["name", "title"],
			as_list=True,
			limit_page_length=500,
		)
	)

	return [
		item
		for item in (
			_option(app_titles.get(app_name) or app_name, app_name)
			for app_name in app_names
		)
		if item
	]


@frappe.whitelist()
def get_bench_options():
	teams = _team_names()
	if not teams:
		return []

	benches = frappe.get_all(
		"Bench",
		filters={
			"team": ("in", teams),
			"status": ("!=", "Archived"),
		},
		fields=["name", "server", "status"],
		order_by="modified desc",
		limit_page_length=500,
	)

	return [
		item
		for item in (
			_option(
				bench.name,
				bench.name,
				" / ".join(filter(None, [bench.server, bench.status])),
			)
			for bench in benches
		)
		if item
	]


@frappe.whitelist()
def get_server_options():
	teams = _team_names()
	if not teams:
		return []

	site_names = _active_site_names(teams)
	app_server_names = set()
	database_server_names = set()

	if site_names:
		site_rows = frappe.get_all(
			"Site",
			filters={"name": ("in", site_names)},
			fields=["server", "bench"],
			limit_page_length=500,
		)
		app_server_names.update(row.server for row in site_rows if row.server)

		bench_names = [row.bench for row in site_rows if row.bench]
		if bench_names:
			bench_rows = frappe.get_all(
				"Bench",
				filters={"name": ("in", bench_names)},
				fields=["server", "database_server"],
				limit_page_length=500,
			)
			app_server_names.update(row.server for row in bench_rows if row.server)
			database_server_names.update(row.database_server for row in bench_rows if row.database_server)

	options = []
	for doctype, server_type in (
		("Server", "App Server"),
		("Database Server", "Database Server"),
	):
		names = app_server_names if doctype == "Server" else database_server_names
		for server in frappe.get_all(
			doctype,
			filters={"name": ("in", list(names)), "status": ("!=", "Archived")} if names else {
				"team": ("in", teams),
				"status": ("!=", "Archived"),
			},
			fields=["name", "title", "status"],
			order_by="modified desc",
			limit_page_length=500,
		):
			item = _option(
				server.title or server.name,
				server.name,
				" / ".join(filter(None, [server_type, server.status])),
			)
			if item:
				options.append(item)

	return options
