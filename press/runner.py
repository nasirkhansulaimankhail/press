import json
import os
import subprocess
import typing
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import frappe
import wrapt
from frappe.model.document import Document
from frappe.utils import now_datetime as now

from press.press.doctype.ansible_play.ansible_play import AnsiblePlay

if typing.TYPE_CHECKING:
	from press.press.doctype.agent_job.agent_job import AgentJob
	from press.press.doctype.virtual_machine.virtual_machine import VirtualMachine


class ExternalAnsibleError(RuntimeError):
	pass


class _RunnerConstants:
	# Keep a narrow compatibility shim for modules that only need Ansible's temp root.
	DEFAULT_LOCAL_TMP = str(Path.home() / ".ansible" / "tmp" / "ansible-local-temp")


constants = _RunnerConstants()


def reconnect_on_failure():
	@wrapt.decorator
	def wrapper(wrapped, instance, args, kwargs):
		try:
			return wrapped(*args, **kwargs)
		except Exception as e:
			if frappe.db.is_interface_error(e):
				frappe.db.connect()
				return wrapped(*args, **kwargs)
			raise

	return wrapper


class AnsibleEventHandler:
	def __init__(self, play: str, tasks: dict[str, dict[str, str]], task_list: list[str]):
		self.play = play
		self.tasks = tasks
		self.task_list = task_list

	def handle_event(self, event: dict):
		event_type = event.get("event")

		if event_type == "play_start":
			self.update_play("Running")
			return

		if event_type == "play_stats":
			self.update_play(stats=event.get("stats") or {})
			return

		if event_type == "task_start":
			self.update_task("Running", role=event.get("role"), task=event.get("task"))
			return

		if event_type == "task_result":
			status = event.get("status")
			result = event.get("result") or {}
			role = event.get("role")
			task = event.get("task")
			self.update_task(status, role=role, task=task, result=result)
			self.process_task_success(event.get("action"), result)
			return

		if event_type == "async_start":
			self.on_async_start(event.get("role"), event.get("task"), event.get("job_id"))
			return

		if event_type == "async_poll":
			self.on_async_poll(event.get("result") or {})
			return

		if event_type == "runner_error":
			self.mark_runner_failure(event.get("message") or "External Ansible runner failed")

	@reconnect_on_failure()
	def process_task_success(self, action: str | None, result: dict):
		if action != "user":
			return

		server_type, server = frappe.db.get_value("Ansible Play", self.play, ["server_type", "server"])
		server = frappe.get_doc(server_type, server)

		if result.get("name") == "root":
			server.root_public_key = result.get("ssh_public_key")
		elif result.get("name") == "frappe":
			server.frappe_public_key = result.get("ssh_public_key")
		else:
			return

		server.save()
		frappe.db.commit()

	@reconnect_on_failure()
	def update_play(self, status: str | None = None, stats: dict | None = None):
		play = frappe.get_doc("Ansible Play", self.play)
		if stats:
			play.update(stats)
			if play.failures or play.unreachable:
				play.status = "Failure"
			else:
				play.status = "Success"
			play.end = now()
			play.duration = play.end - play.start
		else:
			play.status = status
			play.start = now()

		play.save()
		frappe.db.commit()

	@reconnect_on_failure()
	def update_task(self, status: str, role: str | None = None, task: str | None = None, result: dict | None = None):
		task_name = self._get_task_name(role, task)
		if not task_name:
			return

		task_doc = frappe.get_doc("Ansible Task", task_name)
		task_doc.status = status

		if result is not None:
			result = frappe._dict(result)
			task_doc.output = self._coerce_log_value(result.get("stdout"))
			task_doc.error = self._coerce_log_value(result.get("stderr"))
			task_doc.exception = self._coerce_log_value(result.get("msg"))
			for key in ("stdout", "stdout_lines", "stderr", "stderr_lines", "msg"):
				result.pop(key, None)
			task_doc.result = json.dumps(result, indent=4, default=str)
			task_doc.end = now()
			task_doc.duration = task_doc.end - task_doc.start
		else:
			task_doc.start = now()

		task_doc.save()
		self.publish_play_progress(task_doc.name)
		frappe.db.commit()

	@reconnect_on_failure()
	def on_async_start(self, role: str | None, task: str | None, job_id: str | None):
		task_name = self._get_task_name(role, task)
		if not task_name or not job_id:
			return

		task_doc = frappe.get_doc("Ansible Task", task_name)
		task_doc.job_id = job_id
		task_doc.save()
		frappe.db.commit()

	@reconnect_on_failure()
	def on_async_poll(self, result: dict):
		job_id = result.get("ansible_job_id")
		if not job_id:
			return

		task_name = frappe.get_value("Ansible Task", {"play": self.play, "job_id": job_id}, "name")
		if not task_name:
			return

		task_doc = frappe.get_doc("Ansible Task", task_name)
		task_doc.result = json.dumps(result, indent=4, default=str)
		task_doc.duration = now() - task_doc.start
		task_doc.save()
		frappe.db.commit()

	@reconnect_on_failure()
	def mark_runner_failure(self, message: str):
		play = frappe.get_doc("Ansible Play", self.play)
		play.status = "Failure"
		if play.start and not play.end:
			play.end = now()
			play.duration = play.end - play.start
		play.save()

		running_tasks = frappe.get_all(
			"Ansible Task",
			filters={"play": self.play, "status": "Running"},
			order_by="modified desc",
			limit_page_length=1,
			pluck="name",
		)
		if running_tasks:
			task_doc = frappe.get_doc("Ansible Task", running_tasks[0])
			task_doc.status = "Failure"
			task_doc.exception = message
			task_doc.end = now()
			task_doc.duration = task_doc.end - task_doc.start
			task_doc.save()

		frappe.db.commit()

	def publish_play_progress(self, task: str):
		frappe.publish_realtime(
			"ansible_play_progress",
			{"progress": self.task_list.index(task), "total": len(self.task_list), "play": self.play},
			doctype="Ansible Play",
			docname=self.play,
			user=frappe.session.user,
		)

	def _get_task_name(self, role: str | None, task: str | None) -> str | None:
		if not role or not task:
			return None
		return self.tasks.get(role, {}).get(task)

	def _coerce_log_value(self, value):
		if value is None or isinstance(value, str):
			return value
		return json.dumps(value, indent=4, default=str)


class Ansible:
	def __init__(self, server, playbook, user="root", variables=None, port=22):
		self.server = server
		self.playbook = playbook
		self.playbook_path = frappe.get_app_path("press", "playbooks", self.playbook)
		self.host = server.ip if server.ip else server.private_ip
		self.port = port
		self.user = user
		self.variables = variables or {}
		self.ssh_common_args = self._get_ssh_common_args(server)
		self.bridge_python = self._get_bridge_python()
		self.bridge_script = frappe.get_app_path("press", "scripts", "ansible_bridge.py")
		self.create_ansible_play()

	def _get_ssh_common_args(self, server):
		# Keep the SSH transport alive for quiet long-running tasks behind TCP stream proxies.
		args = [
			"-o ServerAliveInterval=30",
			"-o ServerAliveCountMax=6",
			"-o TCPKeepAlive=yes",
		]

		if hasattr(self.server, "bastion_host") and self.server.bastion_host:
			args.append(
				f'-o ProxyCommand="ssh -W %h:%p '
				f"{server.bastion_host.ssh_user}@{server.bastion_host.ip} "
				f'-p {server.bastion_host.ssh_port}"'
			)

		return " ".join(args)

	def _get_bridge_python(self) -> str:
		return (
			os.environ.get("PRESS_ANSIBLE_RUNNER_PYTHON")
			or frappe.conf.get("press_ansible_runner_python")
			or str(Path.home() / ".press-ansible-runner" / "bin" / "python")
		)

	def _build_bridge_command(self, subcommand: str, extra_vars_file: str) -> list[str]:
		command = [
			self.bridge_python,
			self.bridge_script,
			subcommand,
			"--playbook",
			self.playbook_path,
			"--host",
			self.host,
			"--port",
			str(self.port),
			"--user",
			self.user,
			"--extra-vars-file",
			extra_vars_file,
		]
		if self.ssh_common_args:
			command.extend(["--ssh-common-args", self.ssh_common_args])
		return command

	def _run_inspect(self) -> dict:
		with NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
			json.dump(self.variables, handle)
			handle.flush()
			extra_vars_file = handle.name

		try:
			result = subprocess.run(
				self._build_bridge_command("inspect", extra_vars_file),
				capture_output=True,
				text=True,
				check=False,
			)
		finally:
			Path(extra_vars_file).unlink(missing_ok=True)

		payload = self._extract_last_json_line(result.stdout)
		if result.returncode != 0 or not payload:
			message = (result.stderr or result.stdout or "Playbook inspection failed").strip()
			raise ExternalAnsibleError(message)
		return payload

	def _extract_last_json_line(self, output: str) -> dict | None:
		for line in reversed(output.splitlines()):
			line = line.strip()
			if not line:
				continue
			try:
				return json.loads(line)
			except json.JSONDecodeError:
				continue
		return None

	def run(self) -> AnsiblePlay:
		handler = AnsibleEventHandler(self.play, self.tasks, self.task_list)
		bridge_logs: list[str] = []

		with NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
			json.dump(self.variables, handle)
			handle.flush()
			extra_vars_file = handle.name

		try:
			process = subprocess.Popen(
				self._build_bridge_command("run", extra_vars_file),
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
			)

			if process.stdout:
				for raw_line in process.stdout:
					line = raw_line.strip()
					if not line:
						continue
					try:
						event = json.loads(line)
					except json.JSONDecodeError:
						bridge_logs.append(line)
						continue
					handler.handle_event(event)

			returncode = process.wait()
		finally:
			Path(extra_vars_file).unlink(missing_ok=True)

		play = frappe.get_doc("Ansible Play", self.play)
		if returncode != 0 and play.status not in ("Failure", "Success"):
			message = "\n".join(bridge_logs) or "External Ansible runner exited unexpectedly"
			handler.mark_runner_failure(message)
			raise ExternalAnsibleError(message)

		return frappe.get_doc("Ansible Play", self.play)

	def create_ansible_play(self):
		inspection = self._run_inspect()
		play_doc = frappe.get_doc(
			{
				"doctype": "Ansible Play",
				"server_type": self.server.doctype,
				"server": self.server.name,
				"variables": json.dumps(self.variables, indent=4),
				"playbook": self.playbook,
				"play": inspection["play"],
			}
		).insert()

		self.play = play_doc.name
		self.tasks = {}
		self.task_list = []
		for task in inspection.get("tasks", []):
			role = task.get("role")
			name = task.get("task")
			if not role or not name:
				continue

			task_doc = frappe.get_doc(
				{
					"doctype": "Ansible Task",
					"play": self.play,
					"role": role,
					"task": name,
				}
			).insert()
			self.tasks.setdefault(role, {})[name] = task_doc.name
			self.task_list.append(task_doc.name)


class Status(str, Enum):
	Pending = "Pending"
	Running = "Running"
	Success = "Success"
	Skipped = "Skipped"
	Failure = "Failure"

	def __str__(self):
		return self.value


class GenericStep(Document):
	attempt: int
	job_type: Literal["Ansible Play", "Agent Job"]
	job: str | None
	status: Status
	method_name: str


@dataclass
class StepHandler:
	save: Callable
	reload: Callable
	doctype: str
	name: str

	def handle_vm_status_job(
		self,
		step: GenericStep,
		virtual_machine: str,
		expected_status: str,
	) -> None:
		step.attempt = 1 if not step.attempt else step.attempt + 1

		# Try to sync status in every attempt
		try:
			virtual_machine_doc: "VirtualMachine" = frappe.get_doc("Virtual Machine", virtual_machine)
			virtual_machine_doc.sync()
		except Exception:
			pass

		machine_status = frappe.db.get_value("Virtual Machine", virtual_machine, "status")
		step.status = Status.Running if machine_status != expected_status else Status.Success
		step.save()

	def handle_agent_job(self, step: GenericStep, job: str, poll: bool = False) -> None:
		if poll:
			job_doc: AgentJob = frappe.get_doc("Agent Job", job)
			job_doc.get_status()

		job_status = frappe.db.get_value("Agent Job", job, "status")

		status_map = {
			"Delivery Failure": Status.Failure,
			"Undelivered": Status.Pending,
		}
		job_status = status_map.get(job_status, job_status)
		step.attempt = 1 if not step.attempt else step.attempt + 1

		step.status = job_status
		step.save()

		if step.status == Status.Failure:
			raise

	def handle_ansible_play(self, step: GenericStep, ansible: Ansible) -> None:
		step.job_type = "Ansible Play"
		step.job = ansible.play
		step.save()
		ansible_play = ansible.run()
		step.status = ansible_play.status
		step.save()

		if step.status == Status.Failure:
			raise

	def _fail_ansible_step(
		self,
		step: GenericStep,
		ansible: Ansible,
		e: Exception | None = None,
	) -> None:
		step.job_type = "Ansible Play"
		step.job = getattr(ansible, "play", None)
		step.status = Status.Failure
		step.output = str(e)
		step.save()

	def _fail_job_step(self, step: GenericStep, e: Exception | None = None) -> None:
		step.status = Status.Failure
		step.output = str(e)
		step.save()

	def fail(self, failure_status: str = Status.Failure):
		self.status = failure_status
		self.save()
		frappe.db.commit()

	def succeed(self, success_status: str = Status.Success):
		self.status = success_status
		self.save()
		frappe.db.commit()

	def handle_step_failure(self):
		# can be overridden by controllers
		self.error = frappe.get_traceback(with_context=True)
		self.save()

	def get_steps(self, methods: list) -> list[dict]:
		"""Generate a list of steps to be executed for NFS volume attachment."""
		return [
			{
				"step_name": method.__doc__,
				"method_name": method.__name__,
				"status": "Pending",
			}
			for method in methods
		]

	def _get_method(self, method_name: str, method_objects: list[object] | None = None):
		"""Retrieve a method object by name."""
		method_objects = method_objects or []
		for method_object in method_objects:
			if hasattr(method_object, method_name):
				return getattr(method_object, method_name)
		return getattr(self, method_name)
