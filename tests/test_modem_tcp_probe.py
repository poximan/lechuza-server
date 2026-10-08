from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modem-link-monitor"))
from src import tcp_probe


SELECTED = {
    "node-a": ["ar", "Argentina", "Buenos Aires", "192.0.2.1", "AS1"],
    "node-b": ["cl", "Chile", "Santiago", "192.0.2.2", "AS2"],
    "node-c": ["uy", "Uruguay", "Montevideo", "192.0.2.3", "AS3"],
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
        )
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
        self.assertEqual("pendiente", result["nodes"][2]["status"])

    def test_fewer_than_three_nodes_cannot_confirm_closed(self) -> None:
        selected = dict(list(SELECTED.items())[:2])
        failures = {name: [{"error": "Connection refused"}] for name in selected}
        result, _ = self.check(selected, failures)
        self.assertEqual("desconocido", result["state"])


if __name__ == "__main__":
    unittest.main()
