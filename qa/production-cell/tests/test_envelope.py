from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from common import CELL_ROOT, REPO_ROOT, workspace_temporary_directory
from envelope import CommandEnvelope, DockerTarget, _windows_environment_value


class CommandEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = workspace_temporary_directory()
        self.temp_path = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_m23_child_environment_is_fresh_and_drops_ambient_targets(self) -> None:
        parent = dict(os.environ)
        parent.update(
            {
                "PATH": str(self.temp_path / "fake-tools"),
                "DOCKER_HOST": "tcp://198.51.100.1:2375",
                "COMPOSE_FILE": "foreign.yaml",
                "HTTP_PROXY": "http://proxy.invalid",
                "GIT_DIR": "outside",
            }
        )
        envelope = CommandEnvelope(REPO_ROOT, CELL_ROOT, parent, self.temp_path)
        child = envelope._child_environment()
        for forbidden in (
            "DOCKER_HOST",
            "COMPOSE_FILE",
            "HTTP_PROXY",
            "GIT_DIR",
            "COMPOSE_PROJECT_NAME",
        ):
            self.assertNotIn(forbidden, child)
        self.assertEqual(child["COMPOSE_DISABLE_ENV_FILE"], "1")
        self.assertEqual(child["COMPOSE_ANSI"], "never")
        self.assertEqual(child["TEMP"], str(self.temp_path.resolve()))
        self.assertNotIn("fake-tools", child["PATH"])
        if os.name == "nt":
            self.assertEqual(
                Path(child["ProgramFiles"]).name.casefold(), "program files"
            )

    @unittest.skipUnless(
        os.name == "nt", "Windows environment keys are case-insensitive"
    )
    def test_windows_environment_lookup_accepts_normalized_uppercase_keys(self) -> None:
        self.assertEqual(
            _windows_environment_value({"COMSPEC": "value"}, "ComSpec"), "value"
        )

    @unittest.skipUnless(
        os.name == "nt", "Windows environment keys are case-insensitive"
    )
    def test_windows_environment_lookup_denies_conflicting_case_variants(self) -> None:
        with self.assertRaisesRegex(Exception, "conflicting Windows environment"):
            _windows_environment_value({"COMSPEC": "one", "ComSpec": "two"}, "ComSpec")

    def test_m23_every_post_discovery_call_injects_explicit_context(self) -> None:
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        envelope._context = DockerTarget(
            context_name="desktop-linux" if os.name == "nt" else "default",
            endpoint="npipe:////./pipe/dockerDesktopLinuxEngine"
            if os.name == "nt"
            else "unix:///var/run/docker.sock",
            endpoint_kind="npipe" if os.name == "nt" else "unix",
            endpoint_sha256="0" * 64,
            daemon_id="synthetic",
            daemon_name="synthetic",
            server_version="28.0.0",
            os_type="linux",
            daemon_identity_sha256="0" * 64,
        )
        completed = __import__("subprocess").CompletedProcess([], 0, b"", b"")
        with patch.object(envelope, "_run", return_value=completed) as seam:
            envelope.run_docker(["info"])
        args = seam.call_args.args[1]
        self.assertEqual(args[0:2], ["--context", envelope._context.context_name])

    def test_only_read_only_git_commands_are_accepted(self) -> None:
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        with self.assertRaisesRegex(Exception, "read-only"):
            envelope.run_git(["commit", "-m", "forbidden"])

    def test_m14_docker_context_override_is_denied_before_subprocess(self) -> None:
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        envelope._context = DockerTarget(
            context_name="desktop-linux" if os.name == "nt" else "default",
            endpoint="npipe:////./pipe/dockerDesktopLinuxEngine"
            if os.name == "nt"
            else "unix:///var/run/docker.sock",
            endpoint_kind="npipe" if os.name == "nt" else "unix",
            endpoint_sha256="0" * 64,
            daemon_id="synthetic",
            daemon_name="synthetic",
            server_version="28.0.0",
            os_type="linux",
            daemon_identity_sha256="0" * 64,
        )
        with (
            patch.object(envelope, "_run") as seam,
            self.assertRaisesRegex(Exception, "target override"),
        ):
            envelope.run_docker(["--context", "remote", "info"])
        seam.assert_not_called()

    def test_docker_context_mutation_is_denied_before_subprocess(self) -> None:
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        with (
            patch.object(envelope, "_run") as seam,
            self.assertRaisesRegex(Exception, "context mutation"),
        ):
            envelope.run_docker(["context", "use", "remote"])
        seam.assert_not_called()

    def test_reattest_mismatch_keeps_original_context_and_issues_no_delete(self) -> None:
        expected = DockerTarget(
            context_name="desktop-linux" if os.name == "nt" else "default",
            endpoint="npipe:////./pipe/dockerDesktopLinuxEngine"
            if os.name == "nt"
            else "unix:///var/run/docker.sock",
            endpoint_kind="npipe" if os.name == "nt" else "unix",
            endpoint_sha256="0" * 64,
            daemon_id="expected-daemon",
            daemon_name="expected-daemon",
            server_version="28.0.0",
            os_type="linux",
            daemon_identity_sha256="0" * 64,
        )
        changed = DockerTarget(
            context_name=expected.context_name,
            endpoint=expected.endpoint,
            endpoint_kind=expected.endpoint_kind,
            endpoint_sha256=expected.endpoint_sha256,
            daemon_id="changed-daemon",
            daemon_name="changed-daemon",
            server_version=expected.server_version,
            os_type="linux",
            daemon_identity_sha256="1" * 64,
        )
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        envelope._context = expected
        with (
            patch.object(envelope, "_attest_context_candidate", return_value=changed),
            patch.object(envelope, "_run") as seam,
            self.assertRaisesRegex(Exception, "changed during the run"),
        ):
            envelope.reattest_context(expected)
        self.assertIs(envelope._context, expected)
        seam.assert_not_called()

    def test_docker_prune_is_denied_before_subprocess(self) -> None:
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        with (
            patch.object(envelope, "_run") as seam,
            self.assertRaisesRegex(Exception, "subcommand"),
        ):
            envelope.run_docker(["network", "prune"])
        seam.assert_not_called()

    def test_m15_compose_file_override_is_denied_before_subprocess(self) -> None:
        envelope = CommandEnvelope(
            REPO_ROOT, CELL_ROOT, dict(os.environ), self.temp_path
        )
        envelope._context = DockerTarget(
            context_name="desktop-linux" if os.name == "nt" else "default",
            endpoint="npipe:////./pipe/dockerDesktopLinuxEngine"
            if os.name == "nt"
            else "unix:///var/run/docker.sock",
            endpoint_kind="npipe" if os.name == "nt" else "unix",
            endpoint_sha256="0" * 64,
            daemon_id="synthetic",
            daemon_name="synthetic",
            server_version="28.0.0",
            os_type="linux",
            daemon_identity_sha256="0" * 64,
        )
        override = self.temp_path / "override.json"
        override.write_text("{}\n", encoding="utf-8")
        with (
            patch.object(envelope, "_run") as seam,
            self.assertRaisesRegex(Exception, "Compose target override"),
        ):
            envelope.run_compose(
                ["-f", str(self.temp_path / "foreign.yaml"), "config"],
                project_name="msqa025-20260824t000000z-00000000",
                base_file=CELL_ROOT / "compose.yaml",
                override_file=override,
                run_temp=self.temp_path,
            )
        seam.assert_not_called()


if __name__ == "__main__":
    unittest.main()
