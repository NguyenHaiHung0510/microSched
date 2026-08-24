from __future__ import annotations

import json
import unittest

from common import REPO_ROOT, valid_receipt
from receipt_validation import ReceiptValidationError, validate_receipt_object


class ReceiptValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_path = REPO_ROOT / "agent-tasks/025-qa-receipt.schema.json"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))

    def test_green_pass_receipt(self) -> None:
        validate_receipt_object(self.schema, valid_receipt())

    def test_m12_database_url_canary_is_rejected_recursively(self) -> None:
        receipt = valid_receipt()
        receipt["physical_iphone"]["reason"] = "postgresql://role:canary@db:5432/test"
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_m12_secret_shaped_key_is_rejected_recursively(self) -> None:
        receipt = valid_receipt()
        receipt["physical_iphone"]["session_token"] = "canary"
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_m22_display_not_run_token_is_rejected(self) -> None:
        receipt = valid_receipt()
        receipt["physical_iphone"]["status"] = "NOT RUN"
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_m22_missing_required_field_is_rejected(self) -> None:
        receipt = valid_receipt()
        del receipt["cleanup"]["manifest_sha256"]
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_m25_desktop_linux_unix_pair_is_rejected(self) -> None:
        receipt = valid_receipt()
        receipt["docker_target"]["context_name"] = "desktop-linux"
        receipt["docker_target"]["endpoint_kind"] = "unix"
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_m26_uppercase_fixture_separator_is_rejected_by_schema(self) -> None:
        receipt = valid_receipt()
        receipt["fixtures"]["prefix"] = "[QA025:msqa025-20260824T000000Z-00000000]"
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_m27_different_valid_lowercase_fixture_id_is_rejected_semantically(self) -> None:
        receipt = valid_receipt()
        receipt["fixtures"]["prefix"] = "[QA025:msqa025-20260824t000000z-00000001]"
        with self.assertRaisesRegex(
            ReceiptValidationError, "fixtures.prefix run_id"
        ):
            validate_receipt_object(self.schema, receipt)

    def test_phase_duplicates_are_rejected_semantically(self) -> None:
        receipt = valid_receipt()
        receipt["phases"][1]["name"] = receipt["phases"][0]["name"]
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_foreign_sentinel_config_change_is_rejected(self) -> None:
        receipt = valid_receipt()
        receipt["cleanup"]["foreign_sentinel"]["config_sha256_after"] = "1" * 64
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)

    def test_real_email_is_rejected_but_example_invalid_is_allowed(self) -> None:
        receipt = valid_receipt()
        receipt["physical_iphone"]["reason"] = "qa025@example.invalid"
        validate_receipt_object(self.schema, receipt)
        receipt["physical_iphone"]["reason"] = "person@example.com"
        with self.assertRaises(ReceiptValidationError):
            validate_receipt_object(self.schema, receipt)


if __name__ == "__main__":
    unittest.main()
