import http.client
import os
import socket


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str) -> None:
        super().__init__("localhost", timeout=2)
        self.path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


connection = UnixConnection(os.environ["WOL_CONTROL_SOCKET"])
try:
    connection.request("GET", "/health")
    response = connection.getresponse()
    raise SystemExit(0 if response.status == 200 else 1)
finally:
    connection.close()
