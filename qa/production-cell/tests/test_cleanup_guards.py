from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from common import RUN_ID, workspace_temporary_directory
from cell import (
    CellRun,
    _generated_override,
    build_images_and_pull_database,
    cleanup_cell,
    cleanup_sentinel,
)
from contract import CellError, CleanupGuardDenied


class CleanupGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = workspace_temporary_directory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_migration_context_failure_leaves_sentinel_untouched(self) -> None:
        run = object.__new__(CellRun)
        run.manifest_exists = True
        run.docker_target = object()
        run.run_directory = self.root
        run.cleanup_delete_count = 0
        run.cleanup_delete_permitted = False
        run.sentinel = object()
        run._verify_manifest = lambda: {
            "resources": {
                "containers": [],
                "networks": [],
                "volumes": [],
                "images": [],
            }
        }

        class Envelope:
            def reattest_context(self, expected):
                raise CleanupGuardDenied("changed")

        run.envelope = Envelope()
        with patch.object(run, "docker") as docker, self.assertRaises(CleanupGuardDenied):
            cleanup_cell(run)
        docker.assert_not_called()
        cleanup_sentinel(run)
        docker.assert_not_called()

    def test_volume_ownership_is_attested_before_delete(self) -> None:
        from cell import _verify_cleanup_ownership

        run = object.__new__(CellRun)
        run.run_id = RUN_ID
        payload = {
            "resources": {
                "containers": [],
                "networks": [],
                "volumes": ["foreign-volume"],
                "images": [],
            }
        }
        with patch("cell._resource_labels", return_value={}):
            with self.assertRaises(CleanupGuardDenied):
                _verify_cleanup_ownership(run, payload)

    def test_secret_directory_removal_error_prevents_final_pass(self) -> None:
        # The lifecycle helper is required to surface removal failure instead
        # of treating a lingering secret directory as a successful cleanup.
        from cell import remove_run_temp_directory

        with patch("cell.shutil.rmtree", side_effect=OSError("locked")):
            with self.assertRaises(CellError) as caught:
                remove_run_temp_directory(self.root, label="secret directory")
        self.assertEqual(caught.exception.status, "INFRA_ERROR")

    def test_secret_directory_removal_verifies_disappearance(self) -> None:
        from cell import remove_run_temp_directory

        target = self.root / "secrets"
        target.mkdir()
        (target / "value").write_text("synthetic", encoding="utf-8")
        remove_run_temp_directory(target, label="secret directory")
        self.assertFalse(target.exists())

    def test_database_image_is_derived_owned_and_not_a_foreign_pull_delete(self) -> None:
        run = object.__new__(CellRun)
        run.run_id = RUN_ID
        run.repo_root = self.root
        run.secret_directory = self.root / "secrets"
        run.secret_directory.mkdir()
        run.validate_fixture_contract = lambda: None
        override = _generated_override(run)
        db = override["services"]["db"]
        self.assertEqual(db["image"], f"{RUN_ID}-db:candidate")
        self.assertEqual(db["build"]["dockerfile"], "qa/production-cell/db/Dockerfile")
        self.assertEqual(db["labels"]["com.microsched.qa025.run_id"], RUN_ID)

        recorded: list[tuple[str, str]] = []
        run.resources = {
            "containers": [],
            "networks": [],
            "volumes": [],
            "images": [],
        }
        run.app_image_id = None
        run.add_resource = lambda kind, image_id: recorded.append((kind, image_id))
        run.compose = lambda args, timeout: __import__(
            "subprocess"
        ).CompletedProcess(args, 0, b"", b"")
        image_ids = {
            f"{RUN_ID}-db:candidate": "sha256:" + "1" * 64,
            f"{RUN_ID}-app:candidate": "sha256:" + "2" * 64,
            f"{RUN_ID}-helper:candidate": "sha256:" + "3" * 64,
            f"{RUN_ID}-browser:candidate": "sha256:" + "4" * 64,
        }
        docker_calls: list[list[str]] = []

        def docker(args, *, timeout, mutable=False):
            docker_calls.append(args)
            return __import__("subprocess").CompletedProcess(
                args, 0, image_ids[args[-1]].encode("ascii"), b""
            )

        run.docker = docker
        build_images_and_pull_database(run)
        self.assertEqual(recorded[0], ("images", "sha256:" + "1" * 64))
        self.assertFalse(any(call[0] == "pull" for call in docker_calls))
