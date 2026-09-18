import os
import sys
import threading
import unittest
import importlib.util
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "modbus-transport-service" / "src"
os.environ.setdefault("MODBUS_TRANSPORT_API_KEY", "test-key")
os.environ.setdefault("MODBUS_TRANSPORT_QUEUE_MAXSIZE", "8")
os.environ.setdefault("MODBUS_TRANSPORT_WAIT_TIMEOUT_SECONDS", "2")
os.environ.setdefault(
    "MODBUS_TRANSPORT_ENDPOINTS_JSON",
    '[{"name":"test","host":"127.0.0.1","port":502,"timeout_seconds":1,"attempts":1}]',
)

package = types.ModuleType("transport_under_test")
package.__path__ = [str(SERVICE_ROOT)]
sys.modules[package.__name__] = package


def load_module(name):
    qualified = f"transport_under_test.{name}"
    spec = importlib.util.spec_from_file_location(qualified, SERVICE_ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


config_module = load_module("config")
load_module("contracts")
worker_module = load_module("endpoint_worker")
EndpointConfig = config_module.EndpointConfig
load_endpoint_configs = config_module.load_endpoint_configs
EndpointWorker = worker_module.EndpointWorker
WorkItem = worker_module.WorkItem


class ModbusTransportQueueTest(unittest.TestCase):
    def test_fifo_dispatches_one_item_at_a_time(self):
        worker = EndpointWorker(EndpointConfig("test", "127.0.0.1", 502, 1, 1), 8)
        order = []
        release = threading.Event()

        def execute(item):
            order.append(item.caller)
            if item.caller == "first":
                release.wait(1)
            item.result = {"ok": True, "connected": True}
            item.done.set()
            worker.queue.task_done()

        worker._execute_item = execute
        items = [WorkItem(caller=name) for name in ("first", "second", "third")]
        for item in items:
            worker.queue.put(item)
        worker.start()
        release.set()
        for item in items:
            self.assertTrue(item.done.wait(1))
        worker.stop()
        self.assertEqual(order, ["first", "second", "third"])

    def test_cancelled_item_is_not_dispatched(self):
        worker = EndpointWorker(EndpointConfig("test", "127.0.0.1", 502, 1, 1), 8)
        item = WorkItem(caller="cancelled")
        item.cancelled.set()
        worker.queue.put(item)
        worker.start()
        self.assertTrue(item.done.wait(1))
        worker.stop()
        self.assertEqual(worker.completed, 0)
        self.assertEqual(item.result["error"], "consulta cancelada antes del despacho")

    def test_rejects_two_names_for_same_physical_endpoint(self):
        previous = os.environ["MODBUS_TRANSPORT_ENDPOINTS_JSON"]
        os.environ["MODBUS_TRANSPORT_ENDPOINTS_JSON"] = (
            '[{"name":"a","host":"10.0.0.1","port":502,"timeout_seconds":1,"attempts":1},'
            '{"name":"b","host":"10.0.0.1","port":502,"timeout_seconds":1,"attempts":1}]'
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "endpoint fisico"):
                load_endpoint_configs()
        finally:
            os.environ["MODBUS_TRANSPORT_ENDPOINTS_JSON"] = previous


if __name__ == "__main__":
    unittest.main()
