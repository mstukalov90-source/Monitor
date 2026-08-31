"""Tests for genplan photo confirm selection and MSI client."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock
from urllib.parse import urlparse

import httpx

from collector.genplan_photo_confirm import (
    CAM_ID_SQL,
    COUNT_SKIPPED_CAM_SQL,
    COUNT_SKIPPED_NULL_CAM_SQL,
    FALSE_CANDIDATES_SQL,
    FALSE_SNAPSHOT_TABLE,
    PHOTO_UUID_SQL,
    STATUS_ERROR,
    STATUS_SENT,
    STATUS_SKIPPED_CAM,
    TRUE_CANDIDATES_SQL,
    TRUE_SNAPSHOT_TABLES,
    ConfirmCandidate,
    apply_limit,
    exclude_already_sent,
    load_false_candidates,
    load_true_candidates,
    send_confirms,
)
from collector.msi_holes_client import MsiHolesClient


class ConfirmSqlTests(unittest.TestCase):
    def test_true_sql_covers_snapshots_and_requires_cam_id(self) -> None:
        for table in TRUE_SNAPSHOT_TABLES:
            self.assertIn(table, TRUE_CANDIDATES_SQL)
        self.assertIn("crm.tasks_clear", FALSE_CANDIDATES_SQL)
        self.assertNotIn(FALSE_SNAPSHOT_TABLE, TRUE_CANDIDATES_SQL)
        self.assertIn(PHOTO_UUID_SQL, TRUE_CANDIDATES_SQL)
        self.assertIn(f"{CAM_ID_SQL} IS NOT NULL", TRUE_CANDIDATES_SQL)
        self.assertIn("genplan.photo_meta", TRUE_CANDIDATES_SQL)

    def test_false_sql_skips_uuid_and_cam_in_true(self) -> None:
        self.assertIn(FALSE_SNAPSHOT_TABLE, FALSE_CANDIDATES_SQL)
        self.assertIn("tr.photo_uuid = c.photo_uuid", FALSE_CANDIDATES_SQL)
        self.assertIn("tr.cam_id = c.cam_id", FALSE_CANDIDATES_SQL)
        self.assertIn(f"{CAM_ID_SQL} IS NOT NULL", FALSE_CANDIDATES_SQL)

    def test_null_cam_and_skipped_cam_counts(self) -> None:
        self.assertIn("NOT EXISTS", COUNT_SKIPPED_NULL_CAM_SQL)
        self.assertIn(f"{CAM_ID_SQL} IS NOT NULL", COUNT_SKIPPED_NULL_CAM_SQL)
        self.assertIn("tr.cam_id = c.cam_id", COUNT_SKIPPED_CAM_SQL)
        self.assertIn(FALSE_SNAPSHOT_TABLE, COUNT_SKIPPED_CAM_SQL)
        self.assertEqual(STATUS_SKIPPED_CAM, "skipped_cam")

    def test_load_true_executes_true_sql(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("uuid-1", "cam-1")]
        rows = load_true_candidates(cur)
        self.assertEqual(cur.execute.call_args[0][0], TRUE_CANDIDATES_SQL)
        self.assertEqual(rows, [ConfirmCandidate("uuid-1", "cam-1", True)])

    def test_load_false_executes_false_sql(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("uuid-2", "cam-2")]
        rows = load_false_candidates(cur)
        self.assertEqual(cur.execute.call_args[0][0], FALSE_CANDIDATES_SQL)
        self.assertEqual(rows, [ConfirmCandidate("uuid-2", "cam-2", False)])

    def test_blank_cam_id_is_not_a_candidate(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("uuid-1", "")]
        self.assertEqual(load_true_candidates(cur), [])


class ConfirmFilterTests(unittest.TestCase):
    def test_exclude_already_sent_same_confirm(self) -> None:
        rows = [
            ConfirmCandidate("a", "cam1", True),
            ConfirmCandidate("b", "cam2", False),
        ]
        pending, skipped = exclude_already_sent(rows, {"a": True})
        self.assertEqual(skipped, 1)
        self.assertEqual(pending, [rows[1]])

    def test_exclude_allows_confirm_change(self) -> None:
        rows = [ConfirmCandidate("a", "cam1", True)]
        pending, skipped = exclude_already_sent(rows, {"a": False})
        self.assertEqual(skipped, 0)
        self.assertEqual(pending, rows)

    def test_apply_limit_per_bucket(self) -> None:
        rows = [
            ConfirmCandidate(f"u{i}", f"c{i}", True) for i in range(15)
        ]
        limited = apply_limit(rows, 10)
        self.assertEqual(len(limited), 10)
        self.assertEqual(apply_limit(rows, 0), rows)


class ConfirmPhotoClientTests(unittest.TestCase):
    def test_confirm_photo_posts_json(self) -> None:
        recorded: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/oauth2/token"):
                return httpx.Response(
                    200, json={"access_token": "tok", "expires_in": 3600}
                )
            recorded.append(request)
            return httpx.Response(200, json={"ok": True})

        api = MsiHolesClient(
            client_id="id",
            client_secret="secret",
            token_endpoint="https://id.cxm.dev/oauth2/token",
            base_url="https://m2m.msi-holes.cxm.dev",
            transport=httpx.MockTransport(handler),
        )
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        resp = api.confirm_photo(uuid, True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(recorded), 1)
        req = recorded[0]
        self.assertEqual(req.method, "PATCH")
        self.assertEqual(urlparse(str(req.url)).path, f"/api/photos/{uuid}/confirm")
        self.assertEqual(json.loads(req.content.decode()), {"confirm": True})

    def test_confirm_photo_empty_uuid_raises(self) -> None:
        api = MsiHolesClient(
            client_id="id",
            client_secret="secret",
            transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        )
        with self.assertRaises(ValueError):
            api.confirm_photo("  ", False)


class SendConfirmsTests(unittest.TestCase):
    def test_success_upserts_sent(self) -> None:
        api = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        api.confirm_photo.return_value = resp
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        result = send_confirms(
            api,
            conn,
            [ConfirmCandidate("u1", "c1", True), ConfirmCandidate("u2", "c2", False)],
        )
        self.assertEqual(result.sent_true, 1)
        self.assertEqual(result.sent_false, 1)
        self.assertEqual(result.errors, 0)
        self.assertEqual(conn.commit.call_count, 2)
        statuses = [call[0][1][2] for call in cur.execute.call_args_list]
        self.assertEqual(statuses, [STATUS_SENT, STATUS_SENT])

    def test_http_error_writes_error_status(self) -> None:
        api = MagicMock()
        response = MagicMock()
        response.status_code = 500
        api.confirm_photo.side_effect = httpx.HTTPStatusError(
            "boom",
            request=MagicMock(),
            response=response,
        )
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        result = send_confirms(api, conn, [ConfirmCandidate("u1", "c1", True)])
        self.assertEqual(result.sent_true, 0)
        self.assertEqual(result.errors, 1)
        self.assertEqual(cur.execute.call_args[0][1][2], STATUS_ERROR)


if __name__ == "__main__":
    unittest.main()
