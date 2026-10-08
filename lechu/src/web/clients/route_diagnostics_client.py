import ipaddress
import os
import re
import socket
import subprocess
from typing import Any

from src.utils import timebox


_HOP_LINE = re.compile(r"^\s*(\d+)(\??):\s+(.+)$")
_LATENCY = re.compile(r"(\d+(?:\.\d+)?)\s*ms")


class RouteDiagnosticsClient:
    def trace(self, ip: str, port: int) -> dict[str, Any]:
        destination = str(ipaddress.ip_address(ip))
        if not 1 <= port <= 65535:
            raise ValueError("Puerto de destino invalido para diagnostico de ruta")
        tcp = self._check_tcp(destination, port)
        environment = dict(os.environ, LANG="C", LC_ALL="C")
        try:
            completed = subprocess.run(
                ["tracepath", "-n", "-m", "30", "-p", str(port), destination],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "hops": [],
                "probed_hops": 0,
                "reached": False,
                "tcp": tcp,
                "error": f"No se pudo completar tracepath: {exc}",
            }

        hops: dict[int, dict[str, Any]] = {}
        probed_hops = 0
        reached = False
        for line in completed.stdout.splitlines():
            match = _HOP_LINE.match(line)
            if not match or match.group(2) == "?":
                continue
            number = int(match.group(1))
            description = match.group(3)
            if number > 30 or description.startswith("[LOCALHOST]"):
                continue
            probed_hops = max(probed_hops, number)
            if description.startswith("no reply"):
                continue
            address = description.split()[0]
            try:
                address = str(ipaddress.ip_address(address))
            except ValueError:
                continue
            latency = _LATENCY.search(description)
            hops[number] = {
                "number": number,
                "address": address,
                "status": "respuesta",
                "latency_ms": float(latency.group(1)) if latency else None,
            }
            if address == destination:
                reached = True
        error = (
            completed.stderr.strip() or f"tracepath termino con codigo {completed.returncode}"
        ) if completed.returncode != 0 else None
        return {
            "hops": [hops[number] for number in sorted(hops)],
            "probed_hops": probed_hops,
            "reached": reached,
            "tcp": tcp,
            "error": error,
        }

    @staticmethod
    def _check_tcp(ip: str, port: int) -> dict[str, Any]:
        started_at = timebox.monotonic()
        try:
            with socket.create_connection((ip, port), timeout=5):
                pass
        except ConnectionRefusedError:
            return {"status": "rechazado", "latency_ms": None, "error": None}
        except socket.timeout:
            return {"status": "sin_respuesta", "latency_ms": None, "error": None}
        except OSError as exc:
            return {"status": "error", "latency_ms": None, "error": str(exc)}
        return {
            "status": "conectado",
            "latency_ms": round((timebox.monotonic() - started_at) * 1000, 2),
            "error": None,
        }
