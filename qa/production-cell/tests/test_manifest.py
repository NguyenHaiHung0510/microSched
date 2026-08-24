from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import RUN_ID, SHA256, workspace_temporary_directory
from contract import CleanupGuardDenied, sha256_file
from manifest import (
    MANIFEST_SCHEMA,
    read_verified_manifest,
    update_resources,
    verify_manifest_bindings,
    write_manifest,
)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = workspace_temporary_directory()
        self.root = Path(self.temporary.name)
        self.base = self.root / "base.yaml"
        self.override = self.root / "override.json"
        self.base.write_text("services: {}\n", encoding="utf-8")
        self.override.write_text("{}\n", encoding="utf-8")
        self.path = self.root / "run-manifest.json"
        self.payload = {
            "schema": MANIFEST_SCHEMA,
            "run_id": RUN_ID,
            "project_name": RUN_ID,
            "git_sha": "0" * 40,
            "docker_executable_sha256": SHA256,
            "daemon_identity_sha256": SHA256,
            "daemon": {
                "context_name": "default",
                "endpoint_kind": "unix",
                "endpoint_sha256": SHA256,
                "daemon_id": "synthetic-daemon",
                "server_version": "28.0.0",
                "os_type": "linux",
            },
            "compose": {
                "project_directory": str(self.root),
                "files": [
                    {"path": str(self.base), "sha256": sha256_file(self.base)},
                    {"path": str(self.override), "sha256": sha256_file(self.override)},
                ],
            },
            "resources": {
                "containers": [],
                "networks": [],
                "volumes": [],
                "images": [],
            },
        }
        write_manifest(self.path, self.payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_green_manifest_round_trip_and_exact_resource_update(self) -> None:
        update_resources(
            self.path,
            {
                "containers": ["container-id"],
                "networks": [],
                "volumes": [],
                "images": [],
            },
        )
        payload = read_verified_manifest(self.path)
        self.assertEqual(payload["resources"]["containers"], ["container-id"])
        verify_manifest_bindings(
            payload,
            run_id=RUN_ID,
            project_name=RUN_ID,
            daemon_identity_sha256=SHA256,
        )

    def test_m18_one_byte_hash_tamper_is_denied(self) -> None:
        wrapper = json.loads(self.path.read_text(encoding="utf-8"))
        first = wrapper["manifest_sha256"][0]
        wrapper["manifest_sha256"] = ("0" if first != "0" else "1") + wrapper[
            "manifest_sha256"
        ][1:]
        self.path.write_text(json.dumps(wrapper), encoding="utf-8")
        with self.assertRaises(CleanupGuardDenied):
            read_verified_manifest(self.path)

    def test_m19_project_swap_to_sentinel_is_denied(self) -> None:
        payload = read_verified_manifest(self.path)
        payload["project_name"] = "msqa025-20260824T000001Z-11111111"
        write_manifest(self.path, payload)
        with self.assertRaises(CleanupGuardDenied):
            verify_manifest_bindings(
                read_verified_manifest(self.path),
                run_id=RUN_ID,
                project_name=RUN_ID,
                daemon_identity_sha256=SHA256,
            )

    def test_compose_hash_tamper_is_denied(self) -> None:
        payload = read_verified_manifest(self.path)
        self.override.write_text('{"mutated":true}\n', encoding="utf-8")
        with self.assertRaises(CleanupGuardDenied):
            verify_manifest_bindings(
                payload,
                run_id=RUN_ID,
                project_name=RUN_ID,
                daemon_identity_sha256=SHA256,
            )

    def test_candidate_sha_and_executable_binding_tamper_is_denied(self) -> None:
        payload = read_verified_manifest(self.path)
        with self.assertRaisesRegex(CleanupGuardDenied, "candidate SHA"):
            verify_manifest_bindings(
                payload,
                run_id=RUN_ID,
                project_name=RUN_ID,
                daemon_identity_sha256=SHA256,
                git_sha="1" * 40,
            )
        with self.assertRaisesRegex(CleanupGuardDenied, "Docker executable"):
            verify_manifest_bindings(
                payload,
                run_id=RUN_ID,
                project_name=RUN_ID,
                daemon_identity_sha256=SHA256,
                docker_executable_sha256="1" * 64,
            )


if __name__ == "__main__":
    unittest.main()
