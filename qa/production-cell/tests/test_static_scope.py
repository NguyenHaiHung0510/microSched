from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import CELL_ROOT, REPO_ROOT, workspace_temporary_directory


class StaticCellBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose = (CELL_ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.browser = (REPO_ROOT / "frontend/e2e/production-cell/run.mjs").read_text(
            encoding="utf-8"
        )

    def _service_block(self, name: str, next_name: str) -> str:
        return self.compose.split(f"  {name}:\n", 1)[1].split(f"  {next_name}:\n", 1)[0]

    def test_no_env_file_or_compose_interpolation_target(self) -> None:
        self.assertNotIn("env_file:", self.compose)
        self.assertNotIn("${", self.compose)
        self.assertIn(
            "COMPOSE_DISABLE_ENV_FILE", (CELL_ROOT / "envelope.py").read_text()
        )

    def test_dotenv_canary_has_no_input_seam(self) -> None:
        with workspace_temporary_directory() as directory:
            canary = "QA025_DOTENV_CANARY_DO_NOT_LOAD"
            Path(directory, ".env").write_text(
                f"DATABASE_URL={canary}\n", encoding="utf-8"
            )
            combined_source = self.compose + (CELL_ROOT / "cell.py").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(canary, combined_source)
            self.assertNotIn("dotenv", combined_source.casefold())

    def test_seed_and_app_do_not_receive_owner_or_migrator_secrets(self) -> None:
        seed = self._service_block("seed", "app")
        app = self._service_block("app", "browser")
        self.assertNotIn("owner", seed.casefold())
        self.assertNotIn("migrator", seed.casefold())
        self.assertNotIn("owner", app.casefold())
        self.assertNotIn("migrator", app.casefold())
        self.assertIn("app_password", seed)
        self.assertIn("app_url", app)

    def test_migrator_does_not_receive_app_runtime_or_session_secrets(self) -> None:
        migrate = self._service_block("migrate", "seed")
        self.assertIn("migrator_url", migrate)
        self.assertNotIn("app_url", migrate)
        self.assertNotIn("session_token", migrate)
        self.assertNotIn("aes_key", migrate)

    def test_browser_proxy_and_context_are_fixed_and_nonpersistent(self) -> None:
        self.assertIn("hostname: 'app'", self.browser)
        self.assertIn("port: 8000", self.browser)
        self.assertIn("127.0.0.1", self.browser)
        self.assertIn("browser.newContext", self.browser)
        self.assertIn("serviceWorkers: 'allow'", self.browser)
        self.assertIn("/api/readyz", self.browser)
        self.assertIn("readyBody.commit === payload.candidate_sha", self.browser)
        self.assertNotIn("page.route", self.browser)
        self.assertNotIn("channel: 'chrome'", self.browser)
        self.assertNotIn("launchPersistentContext", self.browser)

    def test_browser_helper_uses_node_24_and_locked_frontend_tree(self) -> None:
        dockerfile = (CELL_ROOT / "browser/Dockerfile").read_text(encoding="utf-8")
        lock = json.loads(
            (REPO_ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
        )
        self.assertIn("FROM node:24-bookworm-slim", dockerfile)
        self.assertIn(
            "COPY frontend/package.json frontend/package-lock.json", dockerfile
        )
        self.assertIn("npm ci", dockerfile)
        self.assertIn("playwright install --with-deps chromium", dockerfile)
        self.assertIn("/qa/frontend/run.mjs", dockerfile)
        self.assertEqual(
            lock["packages"]["node_modules/playwright"]["version"], "1.62.1"
        )

    def test_no_docker_socket_privileged_host_or_external_network(self) -> None:
        lowered = self.compose.casefold()
        self.assertNotIn("docker.sock", lowered)
        self.assertNotIn("privileged:", lowered)
        self.assertNotIn("network_mode:", lowered)
        self.assertNotIn("external:", lowered)
        self.assertIn("internal: true", lowered)

    def test_cleanup_has_no_broad_delete_primitive(self) -> None:
        source = (CELL_ROOT / "cell.py").read_text(encoding="utf-8")
        for forbidden in (
            "compose down",
            "system prune",
            "--remove-orphans",
            '"--force"',
        ):
            self.assertNotIn(forbidden, source.casefold())


if __name__ == "__main__":
    unittest.main()
