from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lechu"))
from src.web.clients.route_diagnostics_client import RouteDiagnosticsClient


class RouteDiagnosticsClientTest(unittest.TestCase):
    def test_unanswered_tail_is_not_reported_as_thirty_routers(self) -> None:
        output = "1?: [LOCALHOST] pmtu 1500\n1: 172.23.0.1 0.04ms\n"
        output += "".join(f"{number}: no reply\n" for number in range(2, 31))
        completed = SimpleNamespace(stdout=output, stderr="", returncode=0)
        with (
            patch("src.web.clients.route_diagnostics_client.socket.create_connection"),
            patch("src.web.clients.route_diagnostics_client.subprocess.run", return_value=completed),
        ):
            result = RouteDiagnosticsClient().trace("179.41.21.156", 40000)
        self.assertEqual(30, result["probed_hops"])
        self.assertEqual([1], [hop["number"] for hop in result["hops"]])
        self.assertEqual("conectado", result["tcp"]["status"])
        self.assertFalse(result["reached"])

    def test_destination_reply_and_refused_tcp_remain_distinct(self) -> None:
        completed = SimpleNamespace(
            stdout="1: 172.23.0.1 0.04ms\n2: 179.41.21.156 2.5ms reached\n",
            stderr="",
            returncode=0,
        )
        with (
            patch(
                "src.web.clients.route_diagnostics_client.socket.create_connection",
                side_effect=ConnectionRefusedError(),
            ),
            patch("src.web.clients.route_diagnostics_client.subprocess.run", return_value=completed),
        ):
            result = RouteDiagnosticsClient().trace("179.41.21.156", 40000)
        self.assertTrue(result["reached"])
        self.assertEqual("rechazado", result["tcp"]["status"])


if __name__ == "__main__":
    unittest.main()
