from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

from requests import Timeout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "i20api-service"))
sys.path.insert(0, str(ROOT / "shared/timeauthority-pkg/src"))

from i20api.clock import LOCAL, iso, months_before
from i20api.settings import Settings
from i20api.storage import Storage
from i20api.sync import SyncManager
from i20api.gwf import GwfClient, GwfError
from i20api.location_catalog import LocationCatalog, LocationCatalogError

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


def locations_page(nodes, more=False, cursor=None):
    return {"data": {"locations": {
        "edges": [{"node": node} for node in nodes],
        "pageInfo": {"hasNextPage": more, "endCursor": cursor},
    }}}


class LocationCatalogTest(unittest.TestCase):
    def test_invalid_persisted_catalog_is_not_overwritten_on_start(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            corrupted = {"version": 1, "updated_at": "fecha-invalidaZ", "locations": []}
            storage.put(LocationCatalog.KEY, corrupted)
            with self.assertRaises(LocationCatalogError):
                LocationCatalog(Settings(locations=(), location_mode="all"), storage)
            self.assertEqual(corrupted, storage.get(LocationCatalog.KEY))

    def test_configured_selection_uses_names_from_gwf(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            settings = Settings(locations=({"id": LOCATION, "name": "Nombre local anterior"},))
            catalog = LocationCatalog(settings, storage)
            catalog.replace([{"id": LOCATION, "name": "Nombre actual de GWF"},
                             {"id": "second", "name": "Otro equipo"}], datetime(2026, 10, 7, tzinfo=timezone.utc))
            self.assertEqual([{"id": LOCATION, "name": "Nombre actual de GWF"}], catalog.snapshot()["locations"])

    def test_unknown_configured_id_does_not_replace_previous_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            catalog = LocationCatalog(Settings(locations=({"id": LOCATION},)), storage)
            now = datetime(2026, 10, 7, tzinfo=timezone.utc)
            catalog.replace([{"id": LOCATION, "name": "Equipo disponible"}], now)
            before = catalog.snapshot()
            with self.assertRaises(LocationCatalogError):
                catalog.replace([{"id": "other", "name": "Otro equipo"}], now)
            self.assertEqual(before, catalog.snapshot())


class I20SyncTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = Storage(str(Path(self.directory.name) / "metrics.sqlite3"))
        self.settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},))
        self.now = datetime(2026, 10, 7, 0, 9, tzinfo=LOCAL)
        self.client = Mock(measurements=Mock(return_value=[]),
                           locations=Mock(return_value=[{"id": LOCATION, "name": "LogAluar"}]))
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
        self.client.measurements.side_effect = GwfError("GWF: ServerError")
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

    def test_all_locations_are_discovered_only_during_sync_and_survive_restart(self):
        settings = Settings(locations=(), location_mode="all")
        manager = SyncManager(settings, self.storage, self.client, lambda: self.now)
        self.assertEqual("pending", manager.catalog.snapshot()["catalog"]["state"])
        self.assertEqual([], manager.catalog.snapshot()["locations"])
        self.assertFalse(manager.tick())
        self.client.locations.assert_not_called()
        self.advance(0)
        available = [{"id": LOCATION, "name": "LogAluar"}, {"id": "second", "name": "LogAlamos"}]
        self.client.locations.return_value = available
        self.assertTrue(manager.tick())
        self.client.measurements.assert_called_once_with(months_before(self.now, 2), self.now, [LOCATION, "second"])
        restarted = SyncManager(settings, self.storage, self.client, lambda: self.now)
        self.assertEqual(available, restarted.catalog.snapshot()["locations"])
        self.assertEqual(iso(self.now), restarted.catalog.snapshot()["catalog"]["updated_at"])
        self.assertEqual(1, self.client.locations.call_count)

    def test_empty_catalog_is_available_and_never_queries_empty_measurement_filter(self):
        settings = Settings(locations=(), location_mode="all")
        manager = SyncManager(settings, self.storage, self.client, lambda: self.now)
        self.advance(0)
        self.client.locations.return_value = []
        self.assertTrue(manager.tick())
        self.assertEqual("available", manager.catalog.snapshot()["catalog"]["state"])
        self.assertEqual([], manager.catalog.snapshot()["locations"])
        self.client.measurements.assert_not_called()

    def test_failed_catalog_refresh_preserves_previous_names_and_records_error(self):
        self.manager.catalog.replace([{"id": LOCATION, "name": "Nombre vigente"}], self.now)
        previous = self.manager.catalog.snapshot()
        self.advance(0)
        self.client.locations.side_effect = GwfError("GWF rechazó la consulta de ubicaciones")
        self.manager.tick()
        self.assertEqual(previous, self.manager.catalog.snapshot())
        self.assertEqual("error", self.manager.status()["last_attempt"]["outcome"])
        self.assertIn("ubicaciones", self.manager.status()["last_attempt"]["error"])
        self.client.measurements.assert_not_called()

    def test_catalog_updates_even_when_measurement_download_fails(self):
        self.advance(0)
        self.client.locations.return_value = [{"id": LOCATION, "name": "Nombre actualizado por GWF"}]
        self.client.measurements.side_effect = GwfError("Error de mediciones")
        self.manager.tick()
        self.assertEqual("Nombre actualizado por GWF", self.manager.catalog.snapshot()["locations"][0]["name"])
        self.assertEqual("error", self.manager.status()["last_attempt"]["outcome"])


class GwfClientTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},))
        self.now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.session = Mock()
        self.token = response({"access_token": "test-token", "token_type": "Bearer", "expires_in": 3600})
        self.client = GwfClient(self.settings, "test-client", "test-secret", session=self.session)

    def test_locations_pages_include_logs_without_measurements(self):
        first = {"id": LOCATION, "name": "LogAluar"}
        second = {"id": "second", "name": "LogAlamos"}
        self.session.post.side_effect = [self.token, response(locations_page([first], True, "next")),
                                        response(locations_page([second]))]
        self.assertEqual([first, second], self.client.locations())
        self.assertEqual("next", self.session.post.call_args_list[-1].kwargs["json"]["variables"]["after"])

    def test_locations_repeated_cursor_is_an_error(self):
        self.session.post.side_effect = [self.token, response(locations_page([], True, "same")),
                                        response(locations_page([], True, "same"))]
        with self.assertRaisesRegex(GwfError, "Catálogo o paginación"):
            self.client.locations()

    def test_duplicate_location_ids_do_not_publish_ambiguous_names(self):
        location = {"id": LOCATION, "name": "LogAluar"}
        self.session.post.side_effect = [self.token, response(locations_page([location, location]))]
        with self.assertRaisesRegex(GwfError, "Catálogo o paginación"):
            self.client.locations()

    def test_empty_measurement_location_filter_is_rejected_without_http(self):
        with self.assertRaises(ValueError):
            self.client.measurements(self.now - timedelta(days=1), self.now, [])
        self.session.post.assert_not_called()

    def test_oauth_and_graphql_match_gwf_contract(self):
        self.session.post.side_effect = [self.token, response(page([]))]
        start = self.now - timedelta(days=1)
        self.assertEqual([], self.client.measurements(start, self.now, [LOCATION]))
        token_call, query_call = self.session.post.call_args_list
        self.assertEqual("https://auth.api.gwf.i2owater.com/oauth2/token", token_call.args[0])
        self.assertEqual({
            "grant_type": "client_credentials",
            "scope": "https://inet.api.gwf.i2owater.com/read",
            "client_id": "test-client", "client_secret": "test-secret",
        }, token_call.kwargs["data"])
        self.assertEqual("application/x-www-form-urlencoded", token_call.kwargs["headers"]["Content-Type"])
        self.assertEqual("https://inet.api.gwf.i2owater.com/graphql", query_call.args[0])
        self.assertEqual("Bearer test-token", query_call.kwargs["headers"]["Authorization"])
        variables = query_call.kwargs["json"]["variables"]
        self.assertEqual(5000, variables["first"])
        self.assertIsNone(variables["after"])
        self.assertEqual({"start": iso(start), "end": iso(self.now)}, variables["where"]["when"])
        self.assertEqual({"id": [LOCATION]}, variables["where"]["locations"])
        self.assertEqual("PT15M", variables["where"]["resolution"])

    def test_graphql_error_detail_redacts_credentials_and_token(self):
        self.session.post.side_effect = [self.token, response({"errors": [{
            "errorType": "AccessDenied", "path": ["locationTimeSeries", "measuredAt"],
            "message": "Sin acceso a test-client con test-secret y test-token",
        }]})]
        with self.assertRaises(GwfError) as caught:
            self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION])
        detail = str(caught.exception)
        self.assertIn("AccessDenied", detail)
        self.assertIn("Sin acceso", detail)
        self.assertIn("locationTimeSeries.measuredAt", detail)
        for secret in ("test-client", "test-secret", "test-token"):
            self.assertNotIn(secret, detail)

    def test_missing_token_expiry_does_not_invent_a_lifetime(self):
        self.session.post.return_value = response({"access_token": "test-token", "token_type": "Bearer"})
        with self.assertRaisesRegex(GwfError, "expires_in"):
            self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION])
        self.assertEqual(1, self.session.post.call_count)

    def test_query_timeout_has_provider_context(self):
        self.session.post.side_effect = [self.token, Timeout()]
        with self.assertRaisesRegex(GwfError, "Consulta GWF: tiempo de espera agotado"):
            self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION])

    def test_lowercase_provider_resolution_is_visible_in_local_history(self):
        for configured, received in (("PT15M", "pt15m"), ("RAW", "raw")):
            with self.subTest(resolution=received), tempfile.TemporaryDirectory() as directory:
                settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},), resolution=configured)
                client = GwfClient(settings, "test-client", "test-secret", session=self.session)
                node = {**record(self.now), "resolution": received}
                self.session.post.side_effect = [self.token, response(page([node]))]
                start = self.now - timedelta(days=1)
                rows = client.measurements(start, self.now, [LOCATION])
                self.assertEqual(configured, rows[0]["resolution"])
                storage = Storage(str(Path(directory) / "db"))
                self.assertEqual(1, storage.save(rows, start))
                history = storage.series(LOCATION, start, self.now, configured)
                self.assertEqual(configured, history[0]["resolution"])
                self.assertEqual(0, history[0]["value"])

    def test_different_resolution_is_not_relabelled(self):
        node = {**record(self.now), "resolution": "raw"}
        self.session.post.side_effect = [self.token, response(page([node]))]
        with self.assertRaisesRegex(GwfError, "Respuesta o paginación GWF inválida"):
            self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION])

    def test_pagination_and_millisecond_dates(self):
        self.session.post.side_effect = [self.token, response(page([record(self.now)], True, "next")), response(page([]))]
        rows = self.client.measurements(self.now - timedelta(days=2), self.now, [LOCATION])
        self.assertEqual(1, len(rows))
        calls = self.session.post.call_args_list
        self.assertEqual("next", calls[-1].kwargs["json"]["variables"]["after"])
        start = calls[1].kwargs["json"]["variables"]["where"]["when"]["start"]
        self.assertTrue(start.endswith(".000Z"))
        self.assertEqual(0, rows[0]["value"])

    def test_graphql_http_200_is_an_error_not_empty_data(self):
        self.session.post.side_effect = [self.token, response({"errors": [{"errorType": "ServerError"}]})]
        with self.assertRaisesRegex(GwfError, "ServerError"):
            self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION])

    def test_401_renews_token_once(self):
        self.session.post.side_effect = [self.token, response({}, 401), self.token, response(page([]))]
        self.assertEqual([], self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION]))
        self.assertEqual(4, self.session.post.call_count)

    def test_repeated_cursor_does_not_loop_forever(self):
        self.session.post.side_effect = [self.token, response(page([], True, "same")), response(page([], True, "same"))]
        with self.assertRaisesRegex(GwfError, "paginación"):
            self.client.measurements(self.now - timedelta(days=1), self.now, [LOCATION])

    def test_bad_later_page_does_not_commit_partial_download(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            self.session.post.side_effect = [self.token, response(locations_page([{"id": LOCATION, "name": "LogAluar"}])),
                                            response(page([record(self.now)], True, "next")),
                                            response({"errors": [{"errorType": "ServerError"}]})]
            manager = SyncManager(self.settings, storage, self.client, lambda: self.now)
            manager.run(manual=True)
            self.assertEqual(0, storage.bounds(LOCATION, "PT15M")["count"])


class I20ApiTest(unittest.TestCase):
    def test_local_reads_never_query_gwf_and_range_is_validated(self):
        from fastapi.testclient import TestClient
        from i20api.app import create_app
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "db"))
            settings = Settings(locations=({"id": LOCATION, "name": "LogAluar"},))
            provider = Mock()
            manager = SyncManager(settings, storage, provider)
            manager.catalog.replace([{"id": LOCATION, "name": "LogAluar"}], datetime(2026, 10, 7, tzinfo=timezone.utc))
            app = create_app(settings, storage, manager)
            client = TestClient(app)
            self.assertEqual(200, client.get("/api/caudalimetros").status_code)
            self.assertEqual(400, client.get("/api/measurements", params={"location_id": LOCATION, "start": "bad", "end": "bad"}).status_code)
            self.assertEqual(404, client.get("/api/measurements", params={"location_id": "other", "start": "bad", "end": "bad"}).status_code)
            self.assertEqual(200, client.get("/api/measurements", params={"location_id": LOCATION, "start": "2026-01-01T00:00:00Z", "end": "2026-10-07T00:00:00Z"}).status_code)
            provider.measurements.assert_not_called()
            provider.locations.assert_not_called()


if __name__ == "__main__":
    unittest.main()
