"""Offline workflow contracts run in the existing Repository hooks environment.

PyYAML comes from pre-commit. Smoke cases execute the actual embedded deploy
script with fake HTTP/time; no app, database, Fly, credentials or network calls.
"""

import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import urllib.error

import yaml


WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"
EXPECTED_SHA = "a" * 40


def workflow(name):
    # BaseLoader preserves GitHub's 'on', which YAML 1.1 treats as a boolean.
    return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def group_key(config, context):
    """Fixture model for property/fallback interpolation, not GitHub's engine."""
    def interpolate(match):
        for key in match[1].strip().split(" || "):
            if key not in context:
                raise AssertionError(f"unsupported group property: {key}")
            if context[key]:
                return str(context[key])
        return ""

    return re.sub(r"\$\{\{(.*?)\}\}", interpolate, config["group"])


class WorkflowContracts(unittest.TestCase):
    def test_only_same_pr_and_workflow_share_a_cancellation_group(self):
        groups = []
        for filename in ("ci.yml", "codeql.yml"):
            data = workflow(filename)
            config = data["concurrency"]
            self.assertEqual(config["cancel-in-progress"], "${{ github.event_name == 'pull_request' }}")
            for event, pr, run in (
                ("pull_request", 17, 101), ("pull_request", 17, 102),
                ("pull_request", 18, 103), ("push", None, 17), ("push", None, 18),
            ):
                context = {
                    "github.workflow": data["name"],
                    "github.event_name": event,
                    "github.event.pull_request.number": pr,
                    "github.run_id": run,
                }
                group = group_key(config, context)
                self.assertNotEqual(group, workflow("deploy.yml")["concurrency"]["group"])
                groups.append(((filename, event, pr if pr else run), group))
        for index, (identity, group) in enumerate(groups):
            for other_identity, other_group in groups[index + 1:]:
                self.assertEqual(group == other_group, identity == other_identity)

    def test_existing_check_names_runtime_probe_and_isolated_migration_remain(self):
        ci = workflow("ci.yml")
        self.assertEqual(set(ci["on"]), {"pull_request", "push"})
        self.assertEqual(ci["on"]["push"]["branches"], ["develop"])
        self.assertEqual(
            {key: job["name"] for key, job in ci["jobs"].items()},
            {
                "backend": "Backend checks", "runtime-deps": "Production dependency check",
                "hooks": "Repository hooks", "secret-scan": "Secret scan",
                "frontend": "Frontend checks", "frontend-e2e": "Frontend e2e",
                "migration-qa": "Migration QA",
            },
        )
        self.assertIn(
            "uv run --no-dev python -m scripts.check_mimi_alpha_runtime",
            [s.get("run") for s in ci["jobs"]["runtime-deps"]["steps"]],
        )
        migration = ci["jobs"]["migration-qa"]
        self.assertEqual(migration["services"]["postgres"]["env"]["POSTGRES_DB"], "microsched_ci")
        self.assertIn("uv run alembic downgrade base", [s.get("run") for s in migration["steps"]])
        codeql = workflow("codeql.yml")
        self.assertEqual(codeql["on"], ci["on"])
        self.assertEqual(codeql["jobs"]["analyze"]["name"], "CodeQL (${{ matrix.language }})")

    def test_deploy_is_immediate_on_develop_without_ci_wait_or_cancellation(self):
        deploy = workflow("deploy.yml")
        self.assertEqual(set(deploy["on"]), {"push", "workflow_dispatch"})
        self.assertEqual(deploy["on"]["push"]["branches"], ["develop"])
        self.assertEqual(deploy["concurrency"], {"group": "deploy-production", "cancel-in-progress": "false"})
        job = deploy["jobs"]["deploy"]
        self.assertEqual(job["name"], "Deploy production")
        self.assertNotIn("needs", job)
        self.assertNotIn("if", job)
        for step in job["steps"]:
            self.assertNotIn("alembic", step.get("run", "").lower())


class DeploymentSmoke(unittest.TestCase):
    def run_smoke(self, responses):
        steps = workflow("deploy.yml")["jobs"]["deploy"]["steps"]
        source = next(s["run"] for s in steps if s.get("shell") == "python")
        now, calls, pending, last = [0.0], [], iter(responses), [responses[-1]]

        def urlopen(url, timeout):
            self.assertEqual(url, "https://microsched.fly.dev/api/readyz")
            self.assertEqual(timeout, 10)
            calls.append(now[0])
            last[0] = next(pending, last[0])
            if isinstance(last[0], Exception):
                raise last[0]
            return io.BytesIO(json.dumps(last[0]).encode())

        def sleep(seconds):
            self.assertGreater(seconds, 0)
            self.assertLessEqual(seconds, 15)
            now[0] += seconds

        with (
            patch.dict("os.environ", {"EXPECTED_SHA": EXPECTED_SHA}),
            patch("urllib.request.urlopen", side_effect=urlopen),
            patch("time.monotonic", side_effect=lambda: now[0]),
            patch("time.sleep", side_effect=sleep),
            patch("sys.stdout", io.StringIO()),
        ):
            try:
                exec(compile(source, "deploy.yml:smoke", "exec"), {})
            except SystemExit as error:
                return str(error), calls, now[0]
        return None, calls, now[0]

    def test_exact_ready_revision_passes_once(self):
        error, calls, elapsed = self.run_smoke([{"status": "ok", "db": "up", "commit": EXPECTED_SHA}])
        self.assertIsNone(error)
        self.assertEqual(calls, [0.0])
        self.assertEqual(elapsed, 0)

    def test_db_down_or_missing_cannot_pass_with_ok_status_and_exact_sha(self):
        for db in ("down", None):
            with self.subTest(db=db):
                payload = {"status": "ok", "commit": EXPECTED_SHA}
                if db is not None:
                    payload["db"] = db
                error, calls, elapsed = self.run_smoke([payload])
                self.assertIsNotNone(error, "unready database was accepted")
                self.assertIn("database readiness", error)
                self.assertGreater(len(calls), 1)
                self.assertLessEqual(len(calls), 10)
                self.assertEqual(elapsed, 90)

    def test_wrong_abbreviated_or_missing_sha_cannot_pass(self):
        for commit in ("b" * 40, EXPECTED_SHA[:7], None):
            with self.subTest(commit=commit):
                error, _, elapsed = self.run_smoke([{"status": "ok", "db": "up", "commit": commit}])
                self.assertIn("expected commit", error)
                self.assertEqual(elapsed, 90)

    def test_degraded_status_cannot_pass_with_db_up(self):
        error, _, elapsed = self.run_smoke([{"status": "degraded", "db": "up", "commit": EXPECTED_SHA}])
        self.assertIn("readiness status", error)
        self.assertEqual(elapsed, 90)

    def test_http_error_old_sha_and_db_down_can_recover(self):
        transient = urllib.error.HTTPError("synthetic", 503, "starting", {}, io.BytesIO())
        self.addCleanup(transient.close)
        error, calls, elapsed = self.run_smoke([
            transient,
            {"status": "ok", "db": "up", "commit": "b" * 40},
            {"status": "ok", "db": "down", "commit": EXPECTED_SHA},
            {"status": "ok", "db": "up", "commit": EXPECTED_SHA},
        ])
        self.assertIsNone(error)
        self.assertEqual(calls, [0, 2, 6, 14])
        self.assertEqual(elapsed, 14)

    def test_http_failure_exhausts_bounded_budget(self):
        error, calls, elapsed = self.run_smoke([urllib.error.URLError("synthetic outage")])
        self.assertIn("synthetic outage", error)
        self.assertLessEqual(len(calls), 10)
        self.assertEqual(elapsed, 90)


if __name__ == "__main__":
    unittest.main()
