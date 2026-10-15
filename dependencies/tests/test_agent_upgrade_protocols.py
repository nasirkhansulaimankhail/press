"""Paired Agent contracts against local host-specific integration trees."""

import contextlib
import json
import os
import pathlib
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
from test_upgrade_protocols import TREES, HOSTS, method


@unittest.skipUnless((TREES / "agent-f3").exists(), "Host integration trees not present")
class AgentContracts(unittest.TestCase):
	def test_nested_endpoint_upload_on_all_sixteen_variants(self):
		for host in HOSTS:
			with self.subTest(host=host), tempfile.TemporaryDirectory() as d:
				file = pathlib.Path(d) / "data.sql"
				file.write_bytes(b"local fixture")
				fake = MagicMock()
				namespace = {"os": os, "contextlib": contextlib}
				fn = method(
					TREES / ("agent-" + host) / "agent/site.py", "upload_offsite_backup", namespace, "Site"
				)
				for nested, outer, expected in [
					("http://nested.invalid", "http://legacy.invalid", "http://nested.invalid"),
					(None, "http://legacy.invalid", "http://legacy.invalid"),
					(None, None, None),
				]:
					offsite = {
						"bucket": "bucket",
						"path": "prefix",
						"endpoint_url": outer,
						"auth": {
							"ACCESS_KEY": "fake",
							"SECRET_KEY": "fake",
							"REGION": "r",
							"ENDPOINT_URL": nested,
						},
					}
					with patch.dict("sys.modules", {"boto3": fake}):
						result = fn(
							None, {"database": {"file": "data.sql", "path": str(file)}}, offsite, True
						)
					kw = fake.client.call_args.kwargs
					self.assertEqual(kw.get("endpoint_url"), expected)
					self.assertEqual(kw["region_name"], "r")
					self.assertEqual(result, {"data.sql": "prefix/data.sql"})
					self.assertTrue(file.exists())

	def test_legacy_and_native_build_routes_select_distinct_implementations(self):
		for host in ["f2", "f3"]:
			path = TREES / ("agent-" + host) / "agent/web.py"
			old = MagicMock()
			new = MagicMock()
			mod = types.ModuleType("agent.legacy_uploaded_builder")
			mod.ImageBuilder = old
			data = {"filename": "local.tar.gz"}
			request = types.SimpleNamespace(json=data)
			fn = method(
				path,
				"build_image",
				{"request": request, "ImageBuilder": new, "b64decode": __import__("base64").b64decode},
			)
			with patch.dict("sys.modules", {"agent.legacy_uploaded_builder": mod}):
				fn()
			old.assert_called_once()
			new.assert_not_called()
			request.json = {"dockerfile": "RlJPTSBzY3JhdGNo", "clone_instructions": []}
			fn()
			new.assert_called_once()
			self.assertIn("dockerfile", new.call_args.kwargs)

	def test_all_variants_copy_cached_app_helper(self):
		import shutil

		for host in HOSTS:
			source = TREES / ("agent-" + host) / "agent"
			with tempfile.TemporaryDirectory() as directory:
				root = pathlib.Path(directory)
				config = root / "config"
				config.mkdir()
				output = root / "output"
				output.mkdir()
				(config / "redis").mkdir()
				for name in ["common_site_config.json", "supervisord.conf", ".vimrc"]:
					(config / name).write_text("fixture")
				shutil.copy(source / "build_configs/get_cached_app.py", config / "get_cached_app.py")
				target = types.SimpleNamespace(build_config_path=str(config), build_directory=str(output))
				method(
					source / "builder.py",
					"_copy_build_config_files",
					{"os": os, "shutil": shutil},
					"ContextManager",
				)(target)
				self.assertEqual(
					(output / "get_cached_app.py").read_bytes(), (config / "get_cached_app.py").read_bytes()
				)

	def test_wildcard_list_timeout_is_safe(self):
		for host in HOSTS:
			fn = method(TREES / ("agent-" + host) / "agent/job.py", "_requested_job_timeout")
			for payload, want in [
				([], None),
				([{"domain": "a"}], None),
				({"agent_job_timeout": 42}, 42),
				(None, None),
			]:
				fake = types.ModuleType("flask")
				fake.has_request_context = lambda: True
				fake.request = types.SimpleNamespace(get_json=lambda silent=True: payload)
				with patch.dict("sys.modules", {"flask": fake}):
					self.assertEqual(fn(), want)
			fake.has_request_context = lambda: False
			with patch.dict("sys.modules", {"flask": fake}):
				self.assertIsNone(fn())
