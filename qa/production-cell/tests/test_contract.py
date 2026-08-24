from __future__ import annotations

import os
import shutil
import unittest
from unittest.mock import patch

from common import CELL_ROOT, REPO_ROOT, compose_config
from cell import make_run, preflight
from contract import (
    AssertionFailure,
    GuardDenied,
    assert_migration_gate,
    assert_no_runtime_port_bindings,
    assert_zero_residuals,
    denied_parent_variable_names,
    fixture_label_ledger,
    guard_parent_environment,
    timeout_status_for_phase,
    validate_browser_source,
    validate_compose_config,
    validate_fixture_identity_bindings,
)


class ParentEnvironmentGuardTests(unittest.TestCase):
    def test_m01_database_url_is_denied_by_name_without_value(self) -> None:
        with self.assertRaisesRegex(GuardDenied, "DATABASE_URL") as caught:
            guard_parent_environment({"DATABASE_URL": "do-not-render"})
        self.assertNotIn("do-not-render", str(caught.exception))

    def test_m13_through_m16_remote_docker_and_compose_inputs_are_denied(self) -> None:
        names = {
            "DOCKER_HOST": "ignored",
            "DOCKER_CONTEXT": "ignored",
            "BUILDKIT_HOST": "ignored",
            "COMPOSE_FILE": "ignored",
            "COMPOSE_PROJECT_NAME": "ignored",
            "COMPOSE_PROFILES": "ignored",
        }
        self.assertEqual(denied_parent_variable_names(names), sorted(names))

    def test_m24_git_indirection_is_denied_and_parent_path_is_not_a_target(
        self,
    ) -> None:
        with self.assertRaisesRegex(GuardDenied, "GIT_DIR"):
            guard_parent_environment({"GIT_DIR": "outside", "PATH": "fake-tools"})

    def test_proxy_family_and_case_variants_are_denied(self) -> None:
        names = denied_parent_variable_names(
            {"https_proxy": "ignored", "No_Proxy": "ignored", "ordinary": "ok"}
        )
        self.assertEqual(names, ["HTTPS_PROXY", "NO_PROXY"])


class FixtureIdentityGuardTests(unittest.TestCase):
    def test_m26_uppercase_separator_is_denied_before_run_directory_creation(self) -> None:
        uppercase = "msqa025-20260824T000000Z-00000000"
        run_directory = CELL_ROOT / ".runs" / uppercase
        self.assertFalse(run_directory.exists())
        with self.assertRaisesRegex(GuardDenied, "canonical lowercase"):
            make_run(REPO_ROOT, {}, uppercase)
        self.assertFalse(run_directory.exists())

    def test_m27_different_valid_fixture_id_is_denied_before_git_or_docker(self) -> None:
        run_id = "msqa025-20260824t000000z-aaaaaaaa"
        different_id = "msqa025-20260824t000000z-bbbbbbbb"
        run = make_run(REPO_ROOT, dict(os.environ), run_id)
        try:
            run.receipt["fixtures"]["prefix"] = f"[QA025:{different_id}]"
            run.fixture_labels = fixture_label_ledger(different_id)
            with patch.object(
                run.envelope,
                "verify_git_worktree",
                side_effect=AssertionError("Git must not run after M27"),
            ) as git_seam:
                with self.assertRaisesRegex(GuardDenied, "fixtures.prefix run_id"):
                    preflight(run)
            git_seam.assert_not_called()
            self.assertEqual(run.resources, {
                "containers": [], "networks": [], "volumes": [], "images": []
            })
            self.assertEqual(run.receipt["acceptance"]["025-SAFE-07"], "NOT_RUN")
        finally:
            shutil.rmtree(run.run_directory, ignore_errors=True)

    def test_green_fixture_ledger_binds_every_entry_byte_for_byte(self) -> None:
        run_id = "msqa025-20260824t000000z-00000000"
        validate_fixture_identity_bindings(
            run_id=run_id,
            project_name=run_id,
            cleanup_run_id=run_id,
            cleanup_project_name=run_id,
            fixture_prefix=f"[QA025:{run_id}]",
            fixture_labels=fixture_label_ledger(run_id),
        )

    def test_m27_fixture_ledger_entry_with_different_valid_lowercase_id_is_denied(
        self,
    ) -> None:
        run_id = "msqa025-20260824t000000z-00000000"
        different_id = "msqa025-20260824t000000z-00000001"
        labels = list(fixture_label_ledger(run_id))
        labels[3] = f"[QA025:{different_id}] private-task"
        with self.assertRaisesRegex(GuardDenied, "fixture label ledger entry 3"):
            validate_fixture_identity_bindings(
                run_id=run_id,
                project_name=run_id,
                cleanup_run_id=run_id,
                cleanup_project_name=run_id,
                fixture_prefix=f"[QA025:{run_id}]",
                fixture_labels=labels,
            )


class ComposePolicyTests(unittest.TestCase):
    def test_green_rendered_policy(self) -> None:
        validate_compose_config(compose_config())

    def _assert_mutation_denied(self, mutate) -> None:
        config = compose_config()
        mutate(config)
        with self.assertRaises(GuardDenied):
            validate_compose_config(config)

    def test_m03_app_host_port_is_denied(self) -> None:
        self._assert_mutation_denied(
            lambda config: config["services"]["app"].update({"ports": ["8000:8000"]})
        )

    def test_m04_database_host_port_is_denied(self) -> None:
        self._assert_mutation_denied(
            lambda config: config["services"]["db"].update({"ports": ["5432:5432"]})
        )

    def test_m05_migrator_key_in_app_environment_is_denied(self) -> None:
        def mutate(config) -> None:
            config["services"]["app"]["environment"]["NEON_MIGRATOR_URL"] = "canary"

        self._assert_mutation_denied(mutate)

    def test_m07_enabled_cron_is_denied(self) -> None:
        def mutate(config) -> None:
            config["services"]["app"]["environment"]["ENABLE_INPROCESS_CRON"] = "true"

        self._assert_mutation_denied(mutate)

    def test_m17_migration_success_condition_is_required(self) -> None:
        def mutate(config) -> None:
            config["services"]["app"]["depends_on"]["migrate"]["condition"] = (
                "service_started"
            )

        self._assert_mutation_denied(mutate)

    def test_m20_browser_or_one_shot_port_is_denied(self) -> None:
        self._assert_mutation_denied(
            lambda config: config["services"]["browser"].update(
                {"ports": ["9000:9000"]}
            )
        )

    def test_m21_implicit_default_network_is_denied(self) -> None:
        def mutate(config) -> None:
            del config["services"]["seed"]["networks"]

        self._assert_mutation_denied(mutate)

    def test_m02_non_loopback_http_target_is_denied(self) -> None:
        def mutate(config) -> None:
            config["services"]["app"]["healthcheck"] = {
                "test": ["CMD", "probe", "http://198.51.100.1/ready"]
            }

        self._assert_mutation_denied(mutate)

    def test_literal_database_url_is_denied_even_when_host_is_local(self) -> None:
        def mutate(config) -> None:
            config["services"]["migrate"]["command"] = [
                "postgresql://role:canary@db:5432/microsched"
            ]

        self._assert_mutation_denied(mutate)

    def test_dotenv_and_docker_socket_are_denied(self) -> None:
        def mutate(config) -> None:
            config["services"]["app"]["env_file"] = ".env"

        self._assert_mutation_denied(mutate)


class BrowserPolicyTests(unittest.TestCase):
    def test_green_browser_runner_is_isolated(self) -> None:
        source = (REPO_ROOT / "frontend/e2e/production-cell/run.mjs").read_text(
            encoding="utf-8"
        )
        validate_browser_source(source)

    def test_m09_persistent_or_real_chrome_runner_is_denied(self) -> None:
        source = (REPO_ROOT / "frontend/e2e/production-cell/run.mjs").read_text(
            encoding="utf-8"
        )
        with self.assertRaises(GuardDenied):
            validate_browser_source(
                source.replace("chromium.launch", "launchPersistentContext")
            )

    def test_m02_runner_has_no_caller_supplied_base_url(self) -> None:
        source = (CELL_ROOT / "run.py").read_text(encoding="utf-8")
        self.assertNotIn("--base-url", source)
        self.assertNotIn("--allow-production", source)
        self.assertNotIn("--remote", source)

    def test_m08_no_auth_bypass_route_was_added(self) -> None:
        app_source = (REPO_ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertNotIn("/api/qa/session", app_source)
        self.assertNotIn("test-auth", app_source)


class CleanupVerdictTests(unittest.TestCase):
    def test_green_zero_exact_resources(self) -> None:
        assert_zero_residuals(
            {"containers": 0, "networks": 0, "volumes": 0, "images": 0}
        )

    def test_m10_one_residual_network_blocks_pass(self) -> None:
        with self.assertRaises(AssertionFailure):
            assert_zero_residuals(
                {"containers": 0, "networks": 1, "volumes": 0, "images": 0}
            )


class MigrationGateTests(unittest.TestCase):
    def test_green_app_creation_after_migrate_zero(self) -> None:
        assert_migration_gate(0, "app")

    def test_m17_migration_nonzero_denies_seed_app_and_browser(self) -> None:
        for service in ("seed", "app", "browser"):
            with self.subTest(service=service), self.assertRaises(AssertionFailure):
                assert_migration_gate(17, service)

    def test_migration_not_run_denies_app(self) -> None:
        with self.assertRaises(AssertionFailure):
            assert_migration_gate(None, "app")


class RuntimeTaxonomyTests(unittest.TestCase):
    def test_image_expose_metadata_with_null_binding_is_allowed(self) -> None:
        assert_no_runtime_port_bindings({}, {"8000/tcp": None}, service="app")

    def test_m20_runtime_browser_binding_is_denied(self) -> None:
        with self.assertRaisesRegex(AssertionFailure, "published a host port"):
            assert_no_runtime_port_bindings(
                {"9000/tcp": [{"HostPort": "9000"}]},
                {"9000/tcp": [{"HostPort": "9000"}]},
                service="browser",
            )

    def test_timeout_taxonomy_distinguishes_setup_test_and_cleanup(self) -> None:
        self.assertEqual(timeout_status_for_phase("database"), "SETUP_TIMEOUT")
        self.assertEqual(timeout_status_for_phase("browser"), "TEST_TIMEOUT")
        self.assertEqual(timeout_status_for_phase("cleanup"), "CLEANUP_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
