from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "i20api-service"))
sys.path.insert(0, str(ROOT / "shared/timeauthority-pkg/src"))

from i20api.clock import LOCAL, iso, months_before
from i20api.settings import Settings
from i20api.storage import Storage
from i20api.sync import SyncManager
from i20api.sentryx import SentryxClient, SentryxError

LOCATION = "urn:mwp:location:test"
STREAM = "urn:mwp:datastream:flow-rate"


def record(instant, value=0, identity="zero"):
    return {"id": identity, "location": {"id": LOCATION}, "dataStream": {"id": STREAM, "unit": "l/s"},
            "timestamp": iso(instant), "resolution": "PT15M", "value": value, "min": None, "max": None, "sd": None}


def response(payload, status=200):
    return Mock(ok=status < 400, status_code=status, json=Mock(return_value=payload))


def page(nodes, more=False, cursor=None):
    return {"data": {"locationTimeSeries": {"measuredAt": {
        "edges": [{"node": x} for x in nodes], "pageInfo": {"hasNextPage": more, "endCursor": cursor}}}}}


class I20SyncTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = Storage(str(Path(self.directory.name) / "metrics.sqlite3"))
        self.settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},))
        self.now = datetime(2026, 10, 7, 0, 9, tzinfo=LOCAL)
        self.client = Mock(measurements=Mock(return_value=[]))
        self.manager = SyncManager(self.settings, self.storage, self.client, lambda: self.now)

    def advance(self, hour, minute=10):
        self.now = self.now.replace(hour=hour, minute=minute)

    def test_daily_retry_hours_and_restart_suspension(self):
        self.assertFalse(self.manager.tick())
        self.advance(0)
        self.assertTrue(self.manager.tick())
        self.assertEqual(iso(self.now + timedelta(hours=1)), self.manager.status()["next_attempt_at"])
        self.advance(1, 9)
        self.assertFalse(self.manager.tick())
        self.advance(1)
        self.assertTrue(self.manager.tick())
        self.assertEqual(iso(self.now + timedelta(hours=2)), self.manager.status()["next_attempt_at"])
        self.advance(3)
        self.assertTrue(self.manager.tick())
        restarted = SyncManager(self.settings, self.storage, self.client, lambda: self.now)
        self.advance(23)
        self.assertFalse(restarted.tick())
        self.assertEqual("suspended", restarted.status()["cycle"]["state"])
        self.assertEqual(3, self.client.measurements.call_count)
        self.now = self.now + timedelta(days=1)
        self.advance(0)
        self.assertTrue(restarted.tick())
        self.assertEqual(1, restarted.status()["cycle"]["attempts"])

    def test_zero_completes_cycle_and_duplicate_is_not_new(self):
        self.advance(0)
        self.client.measurements.return_value = [record(self.now)]
        self.assertTrue(self.manager.tick())
        self.assertEqual("new_data", self.manager.status()["last_attempt"]["outcome"])
        self.assertEqual("complete", self.manager.status()["cycle"]["state"])
        self.assertFalse(self.manager.tick())
        self.assertTrue(self.manager.run(manual=True))
        self.assertEqual("no_new_data", self.manager.status()["last_attempt"]["outcome"])
        rows = self.storage.series(LOCATION, self.now - timedelta(days=1), self.now, "PT15M")
        self.assertEqual(0, rows[0]["value"])
        self.assertEqual(1, len(rows))

    def test_manual_while_suspended_preserves_automatic_cycle(self):
        for hour in (0, 1, 3):
            self.advance(hour)
            self.manager.tick()
        before = self.manager.status()["cycle"]
        self.client.measurements.return_value = [record(self.now)]
        self.manager.run(manual=True)
        self.assertEqual(before, self.manager.status()["cycle"])
        self.assertEqual("manual", self.manager.status()["last_attempt"]["source"])

    def test_provider_error_consumes_attempt_but_not_success(self):
        self.advance(0)
        self.client.measurements.side_effect = SentryxError("Sentryx: ServerError")
        self.manager.tick()
        state = self.manager.status()
        self.assertEqual("error", state["last_attempt"]["outcome"])
        self.assertIsNone(state["last_success_at"])
        self.assertEqual(1, state["cycle"]["attempts"])

    def test_calendar_retention_prunes_even_when_provider_fails(self):
        cutoff = months_before(self.now, 2)
        self.storage.save([record(cutoff - timedelta(seconds=1), identity="old"),
                           record(cutoff, identity="boundary")], cutoff - timedelta(days=1))
        self.manager.tick()  # Before the HTTP schedule; local retention still applies.
        self.assertEqual(1, self.storage.bounds(LOCATION, "PT15M")["count"])
        self.assertEqual(iso(cutoff), self.storage.bounds(LOCATION, "PT15M")["first"])
        march = datetime(2026, 3, 31, 10, tzinfo=LOCAL)
        self.assertEqual(28, months_before(march, 1).astimezone(LOCAL).day)
        self.assertEqual(10, months_before(march, 1).astimezone(LOCAL).hour)

    def test_no_overlapping_manual_and_scheduled_downloads(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            release.wait(2)
            return []
        self.client.measurements.side_effect = slow
        self.assertTrue(self.manager.request_manual())
        self.assertTrue(entered.wait(2))
        self.assertFalse(self.manager.request_manual())
        self.assertFalse(self.manager.tick())
        release.set()
        self.manager.thread.join(2)
        self.assertEqual(1, self.client.measurements.call_count)

    def test_interrupted_attempt_remains_consumed_on_restart(self):
        self.advance(0)
        self.storage.put("cycle", {"day": "2026-10-07", "state": "retrying", "attempts": 1,
                                   "retry_at": iso(self.now + timedelta(hours=1))})
        self.storage.put("last_attempt", {"outcome": "running", "source": "automatic"})
        restarted = SyncManager(self.settings, self.storage, self.client, lambda: self.now)
        self.assertEqual("error", restarted.status()["last_attempt"]["outcome"])
        self.assertFalse(restarted.tick())
        self.assertEqual(1, restarted.status()["cycle"]["attempts"])


class SentryxClientTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},))
        self.now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.session = Mock()
        self.token = response({"access_token": "test-token", "expires_in": 3600})
        self.client = SentryxClient(self.settings, "test-client", "test-secret", session=self.session)

    def test_pagination_and_millisecond_dates(self):
        self.session.post.side_effect = [self.token, response(page([record(self.now)], True, "next")), response(page([]))]
        rows = self.client.measurements(self.now - timedelta(days=2), self.now)
        self.assertEqual(1, len(rows))
        calls = self.session.post.call_args_list
        self.assertEqual("next", calls[-1].kwargs["json"]["variables"]["after"])
        start = calls[1].kwargs["json"]["variables"]["where"]["when"]["start"]
        self.assertTrue(start.endswith(".000Z"))
        self.assertEqual(0, rows[0]["value"])

    def test_graphql_http_200_is_an_error_not_empty_data(self):
        self.session.post.side_effect = [self.token, response({"errors": [{"errorType": "ServerError"}]})]
        with self.assertRaisesRegex(SentryxError, "ServerError"):
            self.client.measurements(self.now - timedelta(days=1), self.now)

    def test_401_renews_token_once(self):
        self.session.post.side_effect = [self.token, response({}, 401), self.token, response(page([]))]
        self.assertEqual([], self.client.measurements(self.now - timedelta(days=1), self.now))
        self.assertEqual(4, self.session.post.call_count)

    def test_repeated_cursor_does_not_loop_forever(self):
        self.session.post.side_effect = [self.token, response(page([], True, "same")), response(page([], True, "same"))]
        with self.assertRaisesRegex(SentryxError, "paginación"):
            self.client.measurements(self.now - timedelta(days=1), self.now)

    def test_bad_later_page_does_not_commit_partial_download(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            self.session.post.side_effect = [self.token, response(page([record(self.now)], True, "next")),
                                            response({"errors": [{"errorType": "ServerError"}]})]
            manager = SyncManager(self.settings, storage, self.client, lambda: self.now)
            manager.run(manual=True)
            self.assertEqual(0, storage.bounds(LOCATION, "PT15M")["count"])


class I20ApiTest(unittest.TestCase):
    def test_local_reads_never_query_sentryx_and_range_is_validated(self):
        from fastapi.testclient import TestClient
        from i20api.app import create_app
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},))
            provider = Mock()
            manager = SyncManager(settings, storage, provider)
            app = create_app(settings, storage, manager)
            client = TestClient(app)
            self.assertEqual(200, client.get("/api/caudalimetros").status_code)
            self.assertEqual(400, client.get("/api/measurements", params={"location_id": LOCATION, "start": "bad", "end": "bad"}).status_code)
            self.assertEqual(404, client.get("/api/measurements", params={"location_id": "other", "start": "bad", "end": "bad"}).status_code)
            self.assertEqual(200, client.get("/api/measurements", params={"location_id": LOCATION, "start": "2026-01-01T00:00:00Z", "end": "2026-10-07T00:00:00Z"}).status_code)
            provider.measurements.assert_not_called()


if __name__ == "__main__":
    unittest.main()
