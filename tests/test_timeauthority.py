from datetime import datetime, timezone
import unittest

from timeauthority import TimeAuthority


class TimeAuthorityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = TimeAuthority(
            utc_now_source=lambda: datetime(2026, 7, 27, 2, 30, tzinfo=timezone.utc),
            monotonic_source=lambda: 12.5,
        )

    def test_utc_data_and_utc_minus_three_presentation(self) -> None:
        self.assertEqual("2026-07-27T02:30:00Z", self.authority.utc_iso())
        self.assertEqual(
            "2026-07-26 23:30:00",
            self.authority.format_local(self.authority.utc_now()),
        )
        self.assertEqual(12.5, self.authority.monotonic())

    def test_legacy_naive_timestamp_is_explicitly_utc(self) -> None:
        parsed = self.authority.parse("2026-07-27 02:30:00", assume_utc_on_naive=True)
        self.assertEqual("2026-07-27T02:30:00Z", self.authority.utc_iso(parsed))


if __name__ == "__main__":
    unittest.main()
