import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modem-link-monitor"))
from src.state_store import ConnectionStateStore


class ConnectionStateStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.store = ConnectionStateStore(str(self.path), "192.0.2.1", 40000)

    def test_existing_confirmed_state_acquires_its_historical_timestamp(self):
        self.path.write_text(json.dumps({
            "schema_version": 2, "ip": "192.0.2.1", "port": 40000,
            "state": "abierto", "nodes": [], "ts": "2026-10-21T10:00:00Z",
        }))
        loaded = self.store.load()
        self.assertEqual({"state": "abierto", "ts": "2026-10-21T10:00:00Z"}, loaded["last_confirmed"])
        self.assertEqual([], loaded["attempts"])

    def test_inconclusive_result_retains_a_separate_previous_confirmation(self):
        state = self.store.load()
        state.update(
            state="desconocido",
            last_confirmed={"state": "abierto", "ts": "2026-10-21T10:00:00Z"},
            attempts=[{"number": 1, "nodes": [], "state": "desconocido"}],
            elapsed_seconds=45.5,
        )
        self.store.save(state)
        loaded = self.store.load()
        self.assertEqual("desconocido", loaded["state"])
        self.assertEqual(state["last_confirmed"], loaded["last_confirmed"])
        self.assertEqual(state["attempts"], loaded["attempts"])
        self.assertEqual(45.5, loaded["elapsed_seconds"])

    def test_changed_target_does_not_inherit_the_previous_confirmation(self):
        state = self.store.load()
        state.update(state="abierto", last_confirmed={"state": "abierto", "ts": state["ts"]})
        self.store.save(state)
        other = ConnectionStateStore(str(self.path), "192.0.2.2", 40000).load()
        self.assertEqual("desconocido", other["state"])
        self.assertIsNone(other["last_confirmed"])


if __name__ == "__main__":
    unittest.main()
