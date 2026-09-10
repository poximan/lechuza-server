from pathlib import Path
import sys
import unittest


SERVICE_ROOT = Path(__file__).resolve().parents[1] / "modbus-collector-service"
sys.path.insert(0, str(SERVICE_ROOT))

from src.modbus.micom_relay_reader import MicomRelayReader


class FakeReadOnlyDriver:
    def __init__(self):
        self.calls: list[tuple[int, int, int]] = []

    def read_holding_registers(
        self,
        address: int,
        count: int,
        relay_id: int,
    ) -> list[int]:
        self.calls.append((address, count, relay_id))
        words = [0] * count
        words[0] = address - 14080
        return words

    def disconnect(self) -> None:
        pass


class MicomFaultMapTest(unittest.TestCase):
    def test_fault_scan_uses_decimal_addresses_and_full_records(self):
        driver = FakeReadOnlyDriver()
        reader = MicomRelayReader(driver, object())

        fault = reader.read_latest_fault(relay_id=11, date_format=0)

        self.assertEqual(fault.fault_number, 24)
        self.assertEqual(len(driver.calls), 25)
        self.assertEqual(driver.calls[0], (14080, 15, 11))
        self.assertEqual(driver.calls[-1], (14104, 15, 11))
        self.assertTrue(all(count == 15 for _, count, _ in driver.calls))


if __name__ == "__main__":
    unittest.main()
