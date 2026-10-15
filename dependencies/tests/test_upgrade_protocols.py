"""Execute selected merged methods with fake transports; no host/container operations."""

from __future__ import annotations
import ast, copy, contextlib, json, os, pathlib, tempfile, types, unittest
from unittest.mock import MagicMock, patch

PRESS = pathlib.Path(__file__).resolve().parents[2]
TREES = PRESS.parent
HOSTS = [
	"f3",
	"f2",
	"f1.dev",
	"f1",
	"f21",
	"naya-f1",
	"m1",
	"m1.dev",
	"m2",
	"ms1",
	"n1",
	"n1.dev",
	"n2",
	"naya-n1",
	"r2",
	"l1",
]


class D(dict):
	__getattr__ = dict.get


def method(path, name, namespace=None, parent=None):
	tree = ast.parse(path.read_text())
	nodes = (
		tree.body
		if parent is None
		else next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == parent).body
	)
	node = copy.deepcopy(
		next(x for x in nodes if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name)
	)
	node.decorator_list = []
	module = ast.Module(
		body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node],
		type_ignores=[],
	)
	ast.fix_missing_locations(module)
	ns = dict(namespace or {})
	exec(compile(module, str(path), "exec"), ns)
	return ns[name]


def bucket_module(bucket):
	m = types.ModuleType("press.press.doctype.site_backup.site_backup")
	m.get_backup_bucket = lambda *a, **kw: bucket
	return m


class PressContracts(unittest.TestCase):
	def test_backup_bucket_cluster_default_record_and_global_fallback(self):
		path = PRESS / "press/press/doctype/site_backup/site_backup.py"
		for cluster, default, expected in [
			(D(name="cluster", region="r", endpoint_url="http://local"), D(name="default"), "cluster"),
			(None, D(name="default", endpoint_url="http://default"), "default"),
			(None, None, "configured"),
		]:
			f = MagicMock()
			f._dict = lambda **kw: D(**kw)
			f.db.get_value.side_effect = [cluster, default] if cluster is None else [cluster]
			f.db.get_single_value.side_effect = lambda dt, field: {
				"aws_s3_bucket": "configured",
				"backup_region": "global",
				"offsite_backups_provider": "AWS S3",
			}.get(field)
			result = method(path, "get_backup_bucket", {"frappe": f})("c", region=True)
			self.assertEqual(result["name"], expected)
			self.assertEqual(result["provider"], "AWS S3")

	def test_offsite_payload_nested_auth_and_legacy_endpoint(self):
		f = MagicMock()
		settings = D(aws_s3_bucket="configured", offsite_backups_access_key_id="fake-access")
		settings.get_password = lambda field: "fake-secret"
		f.get_single.return_value = settings
		b = D(name="chosen", region="r", provider="AWS S3", endpoint_url="http://minio.invalid")
		with patch.dict("sys.modules", {"press.press.doctype.site_backup.site_backup": bucket_module(b)}):
			payload = method(PRESS / "press/agent.py", "_get_offsite_backup_config", {"frappe": f}, "Agent")(
				None, "c", "prefix"
			)
		self.assertEqual(payload["auth"]["ENDPOINT_URL"], b.endpoint_url)
		self.assertEqual(payload["endpoint_url"], b.endpoint_url)
		self.assertEqual(payload["auth"]["REGION"], "r")

	def test_tls_payload_uses_decrypted_key(self):
		f = MagicMock()
		cert = D(name="cert", private_key="********", full_chain="chain", intermediate_chain="intermediate")
		cert.get_private_key = lambda: "decrypted-key"
		f.get_doc.return_value = cert
		target = types.SimpleNamespace(create_agent_job=MagicMock())
		method(PRESS / "press/agent.py", "new_host", {"frappe": f}, "Agent")(
			target, D(tls_certificate="cert", domain="a.invalid", site="a")
		)
		self.assertEqual(
			target.create_agent_job.call_args.args[2]["certificate"]["privkey.pem"], "decrypted-key"
		)

	def test_tls_incomplete_payload_rejected(self):
		f = MagicMock()
		cert = D(name="cert", full_chain="", intermediate_chain="chain")
		cert.get_private_key = lambda: "key"
		f.get_doc.return_value = cert
		f.throw.side_effect = ValueError("incomplete")
		target = types.SimpleNamespace(create_agent_job=MagicMock())
		with self.assertRaises(ValueError):
			method(PRESS / "press/agent.py", "new_host", {"frappe": f}, "Agent")(
				target, D(tls_certificate="cert", domain="a.invalid", site="a")
			)
		target.create_agent_job.assert_not_called()

	def test_custom_endpoint_never_streams(self):
		f = MagicMock()
		f.get_cached_value.return_value = 1
		target = types.SimpleNamespace(
			cluster="c", server="s", disable_streaming_backups=False, is_this_version_or_above=lambda v: True
		)
		for bucket, expected in [
			(D(provider="AWS S3", endpoint_url="http://minio.invalid"), False),
			(D(provider="AWS S3", endpoint_url=None), True),
			(D(provider="Other", endpoint_url=None), False),
		]:
			with patch.dict(
				"sys.modules", {"press.press.doctype.site_backup.site_backup": bucket_module(bucket)}
			):
				result = method(
					PRESS / "press/press/doctype/site/site.py",
					"is_streaming_backup_supported",
					{"frappe": f, "STREAMING_BACKUP_REQUIREMENTS": {"minimum_frappe_version": "16"}},
					"Site",
				)(target)
			self.assertEqual(result, expected)

	def test_plan_fixtures_do_not_import_unreviewed_catalog(self):
		fixtures = json.loads((PRESS / "press/fixtures/site_plan.json").read_text())
		self.assertEqual(fixtures, [])

	def test_migration_does_not_push_monitor_rules(self):
		f = types.SimpleNamespace(flags=D(in_migrate=True))
		target = MagicMock()
		method(
			PRESS / "press/press/doctype/prometheus_alert_rule/prometheus_alert_rule.py",
			"on_update",
			{"frappe": f},
			"PrometheusAlertRule",
		)(target)
		target.get_rules.assert_not_called()

	def test_runner_passes_provider_and_preserves_external_bridge(self):
		t = (PRESS / "press/runner.py").read_text()
		self.assertIn('"cloud_provider": server.get("provider")', t)
		self.assertIn('"scripts", "ansible_bridge.py"', t)
		self.assertNotIn("ActionModule.run =", t)

	def test_preparing_and_terminal_events_are_after_commit(self):
		fake = MagicMock()
		target = types.SimpleNamespace(
			name="build",
			doctype="Deploy Candidate Build",
			team="test",
			build_steps=[],
			has_value_changed=lambda field: False,
		)
		run = method(
			PRESS / "press/press/doctype/deploy_candidate_build/deploy_candidate_build.py",
			"on_update",
			{"frappe": fake},
			"DeployCandidateBuild",
		)
		for status, suffix in [
			("Preparing", "steps"),
			("Running", "steps"),
			("Success", "finished"),
			("Failure", "finished"),
		]:
			target.status = status
			run(target)
			self.assertEqual(fake.publish_realtime.call_args.args[0], f"bench_deploy:build:{suffix}")
			self.assertTrue(fake.publish_realtime.call_args.kwargs["after_commit"])

	def test_native_build_keeps_code_server_and_clone_instructions(self):
		fake = MagicMock()
		fake.db.get_value.return_value = "hash"
		fake.get_doc.return_value = types.SimpleNamespace(
			get_repo_url=lambda: "https://example.invalid/repo", branch="version-16"
		)
		candidate = MagicMock()
		candidate.apps = [D(app="frappe", source="src", release="rel")]
		candidate.dependencies = [D(dependency="PYTHON_VERSION", version="3.14")]
		candidate.generate_ssh_keys.return_value = (None, {"public": "fake-public"})
		for key, value in {
			"is_code_server_enabled": True,
			"redis_cache_size": 128,
			"is_redisearch_enabled": False,
			"use_rq_workerpool": False,
			"merge_all_rq_queues": False,
			"merge_default_and_short_rq_queues": False,
			"custom_workers": 0,
			"custom_workers_group": None,
		}.items():
			setattr(candidate, key, value)
		candidate.release_group = types.SimpleNamespace(is_code_server_enabled=True)
		candidate.is_code_server_enabled = False
		candidate.build_token = "fake-token"
		target = MagicMock()
		target.candidate = candidate
		target.no_cache = False
		target.no_push = True
		target._generate_dockerfile.return_value = "FROM scratch"
		target.encode_dockerfile.return_value = "RlJPTSBzY3JhdGNo"
		target._fetch_registry_settings.return_value = D(
			docker_registry_url="registry.invalid",
			docker_registry_username="fake",
			docker_registry_password="fake",
		)
		for key, value in {
			"docker_image_repository": "image",
			"docker_image_tag": "tag",
			"name": "build",
			"deploy_after_build": False,
			"deploy_on_server": None,
			"platform": "x86_64",
			"build_server": "builder",
			"group": "group",
		}.items():
			setattr(target, key, value)
		agent = MagicMock()
		method(
			PRESS / "press/press/doctype/deploy_candidate_build/deploy_candidate_build.py",
			"send_build_instructions_and_add_build_steps",
			{"frappe": fake, "Agent": agent},
			"DeployCandidateBuild",
		)(target)
		payload = agent.return_value.run_build.call_args.args[0]
		json.dumps(payload)
		self.assertTrue(payload["deploy_candidate_params"]["is_code_server_enabled"])
		self.assertEqual(payload["clone_instructions"][0]["branch"], "version-16")
		self.assertEqual(payload["deploy_candidate_params"]["dependencies"], {"PYTHON_VERSION": "3.14"})


if __name__ == "__main__":
	unittest.main()
