"""Tests for genplan UUID API helpers."""

import unittest

from collector.genplan_uuid_api import UuidAlreadyExistsError, normalize_uuid


class TestGenplanUuidApi(unittest.TestCase):
    def test_normalize_uuid_strips(self) -> None:
        self.assertEqual(
            normalize_uuid("  550e8400-e29b-41d4-a716-446655440000  "),
            "550e8400-e29b-41d4-a716-446655440000",
        )

    def test_normalize_uuid_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_uuid("   ")

    def test_uuid_already_exists_is_exception(self) -> None:
        exc = UuidAlreadyExistsError("abc")
        self.assertEqual(str(exc), "abc")


if __name__ == "__main__":
    unittest.main()
