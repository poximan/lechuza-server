from math import sqrt
from pathlib import Path
import sys
import unittest


SERVICE_ROOT = Path(__file__).resolve().parents[1] / "micom-collector-service"
sys.path.insert(0, str(SERVICE_ROOT))

from src.modbus.micom_relay_reader import MicomRelayReader
from src.modbus.modbus_driver import ModbusReadResult
from src.modelo.rele_micom import MicomDisturbanceScale


class DisturbanceReadDriver:
    def __init__(self, result: ModbusReadResult | None = None):
        self.calls: list[tuple[int, int, int]] = []
        self.result = result

    def read_holding_registers_result(
        self,
        address: int,
        count: int,
        relay_id: int,
    ) -> ModbusReadResult:
        self.calls.append((address, count, relay_id))
        return self.result or ModbusReadResult([0] * count)

    def disconnect(self) -> None:
        pass


class MicomDisturbanceMapTest(unittest.TestCase):
    def test_last_page_uses_only_reported_words(self):
        driver = DisturbanceReadDriver()
        reader = MicomRelayReader(driver, object())

        samples = reader._read_selected_samples(11, 0x0A, 7)

        self.assertEqual(
            driver.calls,
            [
                (0x0900, 125, 11),
                (0x097D, 125, 11),
                (0x0A00, 7, 11),
            ],
        )
        self.assertEqual(len(samples), 257)
        self.assertTrue(all(count <= 125 for _, count, _ in driver.calls))

    def test_index_uses_seven_required_words(self):
        reader = MicomRelayReader(DisturbanceReadDriver(), object())

        metadata = reader._parse_disturbance_index([1, 0, 0, 0, 0, 1, 50])

        self.assertEqual(reader.DISTURBANCE_INDEX_WORDS, 7)
        self.assertEqual(metadata["record_number"], 1)
        self.assertEqual(metadata["post_time_frequency_raw"], 50)

    def test_no_record_exception_is_an_empty_inventory(self):
        driver = DisturbanceReadDriver(
            ModbusReadResult(
                registers=None,
                error="respuesta MiCOM EVT_NOK",
                exception_code=0x0F,
            )
        )
        reader = MicomRelayReader(driver, object())

        self.assertEqual(reader.read_disturbance_references(11), [])

    def test_current_scale_uses_square_root_of_two(self):
        scale = MicomDisturbanceScale(
            phase_primary_ct=100,
            earth_primary_ct=50,
            phase_internal_ratio=800,
            earth_internal_ratio=800,
        )

        self.assertAlmostEqual(scale.scale(800, "phase"), 100 * sqrt(2))
        self.assertAlmostEqual(scale.scale(800, "earth"), 50 * sqrt(2))


if __name__ == "__main__":
    unittest.main()
