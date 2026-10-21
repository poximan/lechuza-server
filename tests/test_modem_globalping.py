from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modem-link-monitor"))
from src import globalping_probe


def response(data):
    result = Mock()
    result.json.return_value = data
    return result


def measurement(results, status="finished", protocol="TCP"):
    return {"id": "measurement1", "type": "ping", "target": "192.0.2.1",
            "measurementOptions": {"protocol": protocol, "port": 40000},
            "status": status, "results": results}


def node(country, received=0, status="finished"):
    result = {"status": status}
    if status == "finished":
        result["stats"] = {"total": 1, "rcv": received, "avg": 178 if received else None}
    return {"probe": {"country": country, "city": "city", "asn": 123}, "result": result}


class GlobalpingTcpProbeTest(unittest.TestCase):
    def setUp(self):
        self.clock = 0.0
        self.probe = globalping_probe.GlobalpingTcpProbe("https://api.globalping.io", 20, 5, 10, 10)
        self.probe.session = Mock()
        self.probe.session.post.return_value = response({"id": "measurement1", "probesCount": 3})
        self.addCleanup(patch.stopall)
        patch.object(globalping_probe._TIME, "monotonic", side_effect=lambda: self.clock).start()
        patch.object(globalping_probe.time, "sleep", side_effect=self.advance).start()

    def advance(self, seconds):
        self.clock += seconds

    def test_tcp_connect_confirms_open_without_waiting_for_other_probes(self):
        self.probe.session.get.return_value = response(measurement([
            node("US", 1), node("BR", status="in-progress"), node("DE", status="in-progress"),
        ], status="in-progress"))
        result = self.probe.check("192.0.2.1", 40000)
        self.assertEqual("abierto", result["state"])
        self.assertEqual(0, self.clock)
        self.assertEqual(.178, result["nodes"][0]["latency_seconds"])
        self.assertEqual("no_esperado", result["nodes"][1]["status"])
        body = self.probe.session.post.call_args.kwargs["json"]
        self.assertEqual({"protocol": "TCP", "port": 40000, "packets": 1}, body["measurementOptions"])

    def test_icmp_success_cannot_be_used_as_port_availability(self):
        self.probe.session.get.return_value = response(measurement([node("US", 1)], protocol="ICMP"))
        self.assertEqual("desconocido", self.probe.check("192.0.2.1", 40000)["state"])

    def test_three_completed_connection_failures_require_confirmation(self):
        self.probe.session.get.return_value = response(measurement([node("US"), node("BR"), node("DE")]))
        self.assertEqual("cerrado", self.probe.check("192.0.2.1", 40000)["state"])
        self.assertEqual(10, self.clock)

    def test_probe_internal_failure_cannot_close_the_port(self):
        self.probe.session.get.return_value = response(measurement([
            node("US"), node("BR"), node("DE", status="failed"),
        ]))
        result = self.probe.check("192.0.2.1", 40000)
        self.assertEqual("desconocido", result["state"])
        self.assertEqual("error_nodo", result["nodes"][2]["status"])

    def test_two_probes_do_not_form_a_closed_consensus(self):
        self.probe.session.get.return_value = response(measurement([node("US"), node("BR")]))
        self.assertEqual("desconocido", self.probe.check("192.0.2.1", 40000)["state"])

    def test_empty_results_timeout_is_bounded(self):
        self.probe.session.get.return_value = response(measurement([], status="in-progress"))
        self.assertEqual("desconocido", self.probe.check("192.0.2.1", 40000)["state"])
        self.assertEqual(20, self.clock)

    def test_delayed_connection_timeouts_still_have_time_for_confirmation(self):
        self.probe.result_timeout = 35
        self.probe.session.get.side_effect = lambda *args, **kwargs: response(
            measurement([node("US"), node("BR"), node("DE")]) if self.clock >= 15
            else measurement([], status="in-progress"))
        self.assertEqual("cerrado", self.probe.check("192.0.2.1", 40000)["state"])
        self.assertEqual(25, self.clock)

    def test_transient_polling_failure_can_recover(self):
        self.probe.session.get.side_effect = [requests.Timeout("timeout"),
            response(measurement([node("US", 1)]))]
        self.assertEqual("abierto", self.probe.check("192.0.2.1", 40000)["state"])
        self.assertEqual(5, self.clock)


class ExternalTcpProbeTest(unittest.TestCase):
    def setUp(self):
        self.globalping = Mock()
        self.check_host = Mock()
        self.probe = globalping_probe.ExternalTcpProbe(self.globalping, self.check_host)

    def test_confirmed_primary_result_does_not_call_the_backup(self):
        self.globalping.check.return_value = {"state": "abierto"}
        self.assertEqual("abierto", self.probe.check("192.0.2.1", 40000)["state"])
        self.check_host.check.assert_not_called()

    def test_inconclusive_primary_uses_backup_and_retains_both_attempts(self):
        self.globalping.check.return_value = {"state": "desconocido", "attempts": [
            {"number": 1, "provider": "Globalping", "state": "desconocido"},
        ]}
        self.check_host.check.return_value = {"state": "abierto", "provider": "Check-Host", "attempts": [
            {"number": 1, "provider": "Check-Host", "state": "abierto"},
        ]}
        result = self.probe.check("192.0.2.1", 40000)
        self.assertEqual("abierto", result["state"])
        self.assertEqual([1, 2], [a["number"] for a in result["attempts"]])
        self.assertEqual(["Globalping", "Check-Host"], [a["provider"] for a in result["attempts"]])

    def test_check_host_can_be_selected_explicitly(self):
        self.probe.primary = "check-host"
        self.check_host.check.return_value = {"state": "abierto"}
        self.assertEqual("abierto", self.probe.check("192.0.2.1", 40000)["state"])
        self.globalping.check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
