from __future__ import annotations
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import json
import subprocess
from common import workspace_temporary_directory
from cell import capture_one_shot_failure, start_one_shot
from common import CELL_ROOT
from contract import GuardDenied
from envelope import CommandEnvelope

class DiagnosticLogsTests(unittest.TestCase):
    def test_bounded_exact_container_logs(self):
        CommandEnvelope._assert_docker_argv(["logs", "--tail", "60", "a" * 64])

    def test_foreign_alias_or_unbounded_logs_denied(self):
        for argv in (["logs", "db"], ["logs", "--follow", "a" * 64], ["logs", "--tail", "all", "a" * 64], ["logs", "--tail", "60", "foreign"], ["logs", "--tail", "60", "a" * 64, "b" * 64]):
            with self.subTest(argv=argv), self.assertRaises(GuardDenied):
                CommandEnvelope._assert_docker_argv(argv)

    def test_diagnostic_denies_foreign_or_unregistered_container(self):
        cid = "a" * 64
        run = SimpleNamespace(_verify_manifest=lambda: None, resources={"containers": [cid]}, run_id="owned", docker=lambda *args, **kwargs: self.fail("must not read logs"))
        with patch("cell._resource_labels", return_value={"com.microsched.qa025.run_id": "foreign", "com.docker.compose.project": "foreign"}):
            with self.assertRaises(GuardDenied):
                capture_one_shot_failure(run, "seed", cid, SimpleNamespace(returncode=0), 20)
        run.resources["containers"] = []
        with self.assertRaises(GuardDenied):
            capture_one_shot_failure(run, "seed", cid, SimpleNamespace(returncode=0), 20)

    def test_cli_zero_container_nonzero_keeps_sanitized_diagnostic(self):
        cid = "a" * 64
        with workspace_temporary_directory() as tmp:
            run = SimpleNamespace(_verify_manifest=lambda: None, resources={"containers": [cid]}, run_id="owned", secret_values={"app_password": "synthetic-test-password", "session_token": "synthetic-test-token"}, run_directory=Path(tmp))
            commands = []
            def docker(args, **kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args, 0, b"error synthetic-test-password synthetic-test-token", b"")
            run.docker = docker
            labels = {"com.microsched.qa025.run_id": "owned", "com.docker.compose.project": "owned"}
            with patch("cell._resource_labels", return_value=labels):
                capture_one_shot_failure(run, "seed", cid, SimpleNamespace(returncode=0), 20)
            value = json.loads((Path(tmp) / "one-shot-failure.json").read_text())
            self.assertEqual(value["container_exit"], 20)
            self.assertEqual(value["cli_exit"], 0)
            self.assertNotIn("synthetic-test-password", value["output"])
            self.assertNotIn("synthetic-test-token", value["output"])
            self.assertEqual(commands, [["logs", "--tail", "60", cid]])

    def test_empty_successful_attach_uses_same_owned_container_logs(self):
        cid = "a" * 64
        run = SimpleNamespace(service_containers={"seed": cid}, docker=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, b"", b""))
        output = b'{"status":"PASS"}\n'
        with patch("cell._container_state", return_value={"ExitCode": 0}), patch("cell.owned_one_shot_logs", return_value=subprocess.CompletedProcess([], 0, output, b"")) as logs:
            self.assertEqual(start_one_shot(run, "seed"), output)
            logs.assert_called_once_with(run, cid)

    def test_nonempty_attach_never_reads_logs(self):
        cid = "a" * 64
        output = b'{"status":"PASS"}\n'
        run = SimpleNamespace(service_containers={"seed": cid}, docker=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, output, b""))
        with patch("cell._container_state", return_value={"ExitCode": 0}), patch("cell.owned_one_shot_logs") as logs:
            self.assertEqual(start_one_shot(run, "seed"), output)
            logs.assert_not_called()
