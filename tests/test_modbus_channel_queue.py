from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modbus-collector-service"))
sys.path.insert(0, str(ROOT / "shared/timeauthority-pkg/src"))

from src.modbus.channel_queue import ModbusChannelQueue


class ModbusChannelQueueTest(unittest.TestCase):
    def test_fifo_and_only_one_request_in_flight(self):
        queue = ModbusChannelQueue("test:502")
        entered = threading.Event()
        release = threading.Event()
        order = []
        errors = []

        def worker(name, block=False):
            try:
                with queue.dispatch({"source": name}, lambda: False, lambda: None) as request:
                    order.append(name)
                    if block:
                        entered.set()
                        if not release.wait(3):
                            raise TimeoutError("La prueba no libero la primera consulta")
                    request["succeeded"] = True
            except BaseException as error:
                errors.append(error)

        first = threading.Thread(target=worker, args=("first", True))
        second = threading.Thread(target=worker, args=("second",))
        third = threading.Thread(target=worker, args=("third",))
        first.start()
        self.assertTrue(entered.wait(1))
        second.start()
        deadline = time.monotonic() + 1
        while queue.snapshot()["queue_depth"] != 1 and time.monotonic() < deadline:
            time.sleep(0.001)
        third.start()
        deadline = time.monotonic() + 1
        while queue.snapshot()["queue_depth"] != 2 and time.monotonic() < deadline:
            time.sleep(0.001)
        snapshot = queue.snapshot()
        release.set()
        for thread in (first, second, third):
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(snapshot["current"]["source"], "first")
        self.assertEqual([item["source"] for item in snapshot["next"]], ["second", "third"])
        self.assertEqual(order, ["first", "second", "third"])
        self.assertEqual(queue.snapshot()["completed"], 3)

    def test_failure_releases_channel_and_records_error(self):
        queue = ModbusChannelQueue("test:502")
        with self.assertRaises(TimeoutError):
            with queue.dispatch({}, lambda: False, lambda: None):
                raise TimeoutError("sin respuesta")
        with queue.dispatch({}, lambda: False, lambda: None) as request:
            request["succeeded"] = True
        self.assertEqual(queue.snapshot()["failed"], 1)
        self.assertIsNone(queue.snapshot()["current"])

    def test_cancelled_request_is_removed(self):
        queue = ModbusChannelQueue("test:502")
        with self.assertRaises(RuntimeError):
            with queue.dispatch({}, lambda: True, lambda: None):
                self.fail("No debe despachar al apagar")
        self.assertEqual(queue.snapshot()["queue_depth"], 0)


if __name__ == "__main__":
    unittest.main()
