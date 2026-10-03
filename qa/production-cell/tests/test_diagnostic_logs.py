from __future__ import annotations
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from cell import capture_one_shot_failure
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
