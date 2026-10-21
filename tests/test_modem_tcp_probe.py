from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modem-link-monitor"))
from src import tcp_probe


SELECTED = {
    "node-a": ["ar", "Argentina", "Buenos Aires", "192.0.2.1", "AS1"],
    "node-b": ["cl", "Chile", "Santiago", "192.0.2.2", "AS2"],
    "node-c": ["uy", "Uruguay", "Montevideo", "192.0.2.3", "AS3"],
}
CATALOG = {
    name: {"location": data[:3], "ip": data[3], "asn": data[4]}
    for name, data in {
        **SELECTED,
        "node-d": ["de", "Germany", "Berlin", "192.0.2.4", "AS4"],
        "node-e": ["us", "USA", "New York", "192.0.2.5", "AS5"],
        "node-f": ["br", "Brazil", "Sao Paulo", "192.0.2.6", "AS6"],
    }.items()
}


class TcpProbeConsensusTest(unittest.TestCase):
    def check(self, selected: dict, results: dict) -> tuple[dict, float]:
        clock = [0.0]
        probe = tcp_probe.TcpProbe(
            base_url="https://check-host.net",
            max_nodes=3,
            failure_confirmation=10,
            result_timeout=20,
            poll_interval=5,
            request_timeout=10,
            max_attempts=1,
        )
        probe._catalog = CATALOG
        probe._catalog_expires = float("inf")
        with (
            patch.object(probe, "_start_check", return_value=("request", selected)),
            patch.object(probe, "_fetch_results", return_value=results),
            patch.object(tcp_probe.time_provider, "monotonic", side_effect=lambda: clock[0]),
            patch.object(tcp_probe.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)),
        ):
            return probe.check("179.41.21.156", 40000), clock[0]

    def test_one_connection_opens_even_when_two_nodes_fail(self) -> None:
        result, elapsed = self.check(SELECTED, {
            "node-a": [{"time": 11.5}],
            "node-b": [{"error": "Connection timed out"}],
            "node-c": [{"error": "Connection refused"}],
        })
        self.assertEqual("abierto", result["state"])
        self.assertEqual(0, elapsed)
        self.assertEqual("conectado", result["nodes"][0]["status"])
        self.assertEqual(11.5, result["nodes"][0]["latency_seconds"])

    def test_three_explicit_failures_close_after_ten_seconds(self) -> None:
        failures = {name: [{"error": "Connection timed out"}] for name in SELECTED}
        result, elapsed = self.check(SELECTED, failures)
        self.assertEqual("cerrado", result["state"])
        self.assertEqual(10, elapsed)

    def test_two_failures_and_one_pending_are_unknown(self) -> None:
        result, elapsed = self.check(SELECTED, {
            "node-a": [{"error": "Connection refused"}],
            "node-b": [{"error": "Connection timed out"}],
            "node-c": None,
        })
        self.assertEqual("desconocido", result["state"])
        self.assertEqual(20, elapsed)
        self.assertEqual("sin_resultado", result["nodes"][2]["status"])

    def test_fewer_than_three_nodes_cannot_confirm_closed(self) -> None:
        selected = dict(list(SELECTED.items())[:2])
        failures = {name: [{"error": "Connection refused"}] for name in selected}
        result, _ = self.check(selected, failures)
        self.assertEqual("desconocido", result["state"])

    def test_one_connection_does_not_wait_for_silent_nodes(self) -> None:
        result, elapsed = self.check(SELECTED, {"node-a": [{"time": 0.0}]})
        self.assertEqual("abierto", result["state"])
        self.assertEqual(0, elapsed)
        self.assertEqual("no_esperado", result["nodes"][1]["status"])

    def test_internal_node_errors_cannot_confirm_a_target_outage(self) -> None:
        result, _ = self.check(SELECTED, {
            name: [{"error": "Too many open files"}] for name in SELECTED
        })
        self.assertEqual("desconocido", result["state"])
        self.assertTrue(all(node["status"] == "error_nodo" for node in result["nodes"]))


class TcpProbeRotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = 0.0
        self.probe = tcp_probe.TcpProbe("https://check-host.net", 3, 10, 20, 5, 10)
        self.probe._catalog = CATALOG.copy()
        self.probe._catalog_expires = float("inf")
        self.selected: dict[str, dict] = {}
        self.addCleanup(patch.stopall)
        patch.object(tcp_probe.time_provider, "monotonic", side_effect=lambda: self.clock).start()
        patch.object(tcp_probe.time, "sleep", side_effect=self.advance).start()
        patch.object(self.probe, "_start_check", side_effect=self.start).start()

    def advance(self, seconds: float) -> None:
        self.clock += seconds

    def start(self, host: str, port: int, nodes: list[str]) -> tuple[str, dict]:
        request_id = str(len(self.selected) + 1)
        selected = {}
        for name in nodes:
            metadata = CATALOG[name]
            selected[name] = [*metadata["location"], metadata["ip"], metadata["asn"]]
        self.selected[request_id] = selected
        return request_id, selected

    def test_timeout_retries_with_disjoint_nodes_and_retains_both_attempts(self) -> None:
        def results(request_id: str, deadline: float) -> dict:
            if request_id == "1":
                return {name: None for name in self.selected[request_id]}
            return {name: [{"time": .25}] for name in self.selected[request_id]}
        with patch.object(self.probe, "_fetch_results", side_effect=results):
            result = self.probe.check("179.41.21.156", 40000)
        self.assertEqual("abierto", result["state"])
        self.assertEqual(20, self.clock)
        self.assertEqual(2, len(result["attempts"]))
        self.assertFalse(set(self.selected["1"]) & set(self.selected["2"]))
        self.assertTrue(all(node["status"] == "sin_resultado" for node in result["attempts"][0]["nodes"]))

    def test_internal_errors_cool_down_but_connections_and_target_failures_do_not(self) -> None:
        def results(request_id: str, deadline: float) -> dict:
            if request_id == "1":
                return {name: [{"error": "Too many open files"}] for name in self.selected[request_id]}
            names = list(self.selected[request_id])
            return {names[0]: [{"time": .1}], names[1]: [{"error": "Connection refused"}]}
        with patch.object(self.probe, "_fetch_results", side_effect=results):
            self.assertEqual("abierto", self.probe.check("179.41.21.156", 40000)["state"])
        self.assertEqual(set(self.selected["1"]), set(self.probe._cooldown_until))
        self.assertEqual(set(self.selected["2"]), set(self.probe._choose_nodes(set())))
        self.clock = 901
        self.assertEqual(set(self.selected["1"]), set(self.probe._choose_nodes(set())))

    def test_completed_checks_rotate_across_cycles(self) -> None:
        with patch.object(self.probe, "_fetch_results", side_effect=lambda request_id, deadline: {
            name: [{"time": .1}] for name in self.selected[request_id]
        }):
            self.probe.check("179.41.21.156", 40000)
            self.advance(300)
            self.probe.check("179.41.21.156", 40000)
        self.assertFalse(set(self.selected["1"]) & set(self.selected["2"]))
        self.assertFalse(self.probe._cooldown_until)

    def test_confirmation_starts_when_all_failures_are_observed(self) -> None:
        def results(request_id: str, deadline: float) -> dict:
            if self.clock < 15:
                return {}
            return {name: [{"error": "Connection refused"}] for name in self.selected[request_id]}
        self.probe.max_attempts = 1
        with patch.object(self.probe, "_fetch_results", side_effect=results):
            result = self.probe.check("179.41.21.156", 40000)
        self.assertEqual("desconocido", result["state"])
        self.assertEqual(20, self.clock)

    def test_rate_limit_stops_the_cycle_without_more_requests(self) -> None:
        response = Mock(status_code=429)
        error = requests.HTTPError("rate limited", response=response)
        with patch.object(self.probe, "_fetch_results", side_effect=error) as fetch:
            result = self.probe.check("179.41.21.156", 40000)
        self.assertEqual("desconocido", result["state"])
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(1, len(result["attempts"]))

    def test_no_cooling_nodes_are_reused_when_all_are_unavailable(self) -> None:
        self.probe._cooldown_until = {name: 900 for name in CATALOG}
        result = self.probe.check("179.41.21.156", 40000)
        self.assertEqual("desconocido", result["state"])
        self.assertFalse(self.selected)


class TcpProbeHttpContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.probe = tcp_probe.TcpProbe("https://check-host.net", 3, 10, 20, 5, 10)
        self.probe.session = Mock()

    def test_explicit_nodes_are_sent_using_the_documented_parameter(self) -> None:
        self.probe.session.get.return_value.json.return_value = {
            "ok": 1, "request_id": "r", "nodes": SELECTED,
        }
        self.probe._start_check("179.41.21.156", 40000, list(SELECTED))
        params = self.probe.session.get.call_args.kwargs["params"]
        self.assertEqual(list(SELECTED), params["node"])
        self.assertEqual("179.41.21.156:40000", params["host"])

    def test_catalog_is_cached_and_cached_nodes_survive_a_refresh_error(self) -> None:
        now = [100.0]
        self.probe.session.get.return_value.json.return_value = {"nodes": CATALOG}
        with patch.object(tcp_probe.time_provider, "monotonic", side_effect=lambda: now[0]):
            self.probe._refresh_nodes()
            self.probe._refresh_nodes()
            self.assertEqual(1, self.probe.session.get.call_count)
            now[0] += 3601
            self.probe.session.get.side_effect = requests.Timeout("provider unavailable")
            self.probe._refresh_nodes()
            self.assertEqual(CATALOG, self.probe._catalog)
            now[0] += 61
            self.probe.session.get.side_effect = None
            self.probe.session.get.return_value.json.return_value = {"nodes": {"invalid": {}}}
            self.probe._refresh_nodes()
            self.assertEqual(CATALOG, self.probe._catalog)

    def test_result_request_timeout_respects_the_remaining_polling_budget(self) -> None:
        self.probe.session.get.return_value.json.return_value = {}
        with patch.object(tcp_probe.time_provider, "monotonic", return_value=19):
            self.probe._fetch_results("r", 20)
        self.assertEqual(1, self.probe.session.get.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
