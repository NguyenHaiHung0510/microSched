from __future__ import annotations

import unittest

from common import CELL_ROOT  # initializes the QA cell import path
from cell import create_service
from contract import GuardDenied
from envelope import CommandEnvelope


class CreateCompatibilityTests(unittest.TestCase):
    def test_only_fixed_create_without_start_is_allowed(self) -> None:
        CommandEnvelope._assert_compose_argv(
            ["up", "--no-start", "--no-deps", "--no-build", "db"]
        )

    def test_up_cannot_start_build_or_expand_services(self) -> None:
        for args in (
            ["up", "db"],
            ["up", "--no-start", "--no-build", "db"],
            ["up", "--no-start", "--no-deps", "--no-build", "app", "db"],
            ["up", "--no-start", "--no-deps", "--no-build", "--remove-orphans", "db"],
        ):
            with self.subTest(args=args), self.assertRaises(GuardDenied):
                CommandEnvelope._assert_compose_argv(args)

    def test_migration_gate_runs_before_any_command(self) -> None:
        class Run:
            migration_exit_code = None
            called = False

            def compose(self, *args, **kwargs):
                self.called = True
                raise AssertionError("must not reach compose")

        run = Run()
        with self.assertRaises(Exception) as caught:
            create_service(run, "app")
        self.assertIn("successful migration", str(caught.exception))
        self.assertFalse(run.called)
