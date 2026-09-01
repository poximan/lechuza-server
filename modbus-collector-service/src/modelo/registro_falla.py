from datetime import datetime, timedelta, timezone

from logosaurio import Logosaurio


class RegistroFalla:
    """Decodifica un registro de falla MiCOM segun su formato declarado."""

    DATE_FORMAT_PRIVATE = 0
    DATE_FORMAT_IEC_870 = 1
    PRIVATE_EPOCH = datetime(1994, 1, 1, tzinfo=timezone.utc)
    PRIVATE_LAST_YEAR = 2093

    def __init__(
        self,
        raw_registers: list[int],
        date_format: int,
        logger: Logosaurio,
    ):
        if len(raw_registers) != 15:
            raise ValueError(
                "Se esperaban 15 registros Modbus, "
                f"pero se recibieron {len(raw_registers)}."
            )
        if any(word < 0 or word > 0xFFFF for word in raw_registers):
            raise ValueError("El registro de falla contiene palabras fuera de 16 bits")

        self.logger = logger
        self._raw_registers = raw_registers
        if date_format == self.DATE_FORMAT_PRIVATE:
            self.timestamp_format = "private"
            self._parse_private_timestamp()
        elif date_format == self.DATE_FORMAT_IEC_870:
            self.timestamp_format = "iec870"
            self._parse_iec_timestamp()
        else:
            raise ValueError(f"Formato de fecha MiCOM desconocido: {date_format}")
        self._parse_fault_values()

    @staticmethod
    def _unsigned_32_lsw_first(low_word: int, high_word: int) -> int:
        return (high_word << 16) | low_word

    def _parse_private_timestamp(self) -> None:
        self.fault_number = self._raw_registers[0]
        seconds_since_epoch = self._unsigned_32_lsw_first(
            self._raw_registers[1],
            self._raw_registers[2],
        )
        self.fault_milliseconds_raw = self._unsigned_32_lsw_first(
            self._raw_registers[3],
            self._raw_registers[4],
        )
        if not 0 <= self.fault_milliseconds_raw <= 999:
            raise ValueError(
                "Milisegundos privados fuera de rango: "
                f"{self.fault_milliseconds_raw}"
            )

        self.fault_datetime = self.PRIVATE_EPOCH + timedelta(
            seconds=seconds_since_epoch,
            milliseconds=self.fault_milliseconds_raw,
        )
        if self.fault_datetime.year > self.PRIVATE_LAST_YEAR:
            raise ValueError(
                "Fecha privada fuera del rango MiCOM: "
                f"{self.fault_datetime.isoformat()}"
            )
        self._set_datetime_parts()

    def _parse_iec_timestamp(self) -> None:
        self.fault_number = self._raw_registers[0]

        year_word = self._raw_registers[1]
        year_high = (year_word >> 8) & 0x7F
        year_low = year_word & 0x7F
        if 94 <= year_high <= 99:
            self.fault_year = 1900 + year_high
        elif 0 <= year_low <= 93:
            self.fault_year = 2000 + year_low
        else:
            raise ValueError(
                f"Año IEC de falla fuera de rango: 0x{year_word:04X}"
            )

        date_word = self._raw_registers[2]
        self.fault_month = (date_word >> 8) & 0x0F
        self.fault_day = date_word & 0x1F

        time_word = self._raw_registers[3]
        self.fault_hour = (time_word >> 8) & 0x1F
        self.fault_minute = time_word & 0x3F

        self.fault_milliseconds_raw = self._raw_registers[4]
        if not 0 <= self.fault_milliseconds_raw <= 59999:
            raise ValueError(
                "Milisegundos dentro del minuto fuera de rango: "
                f"{self.fault_milliseconds_raw}"
            )
        self.fault_seconds, milliseconds = divmod(
            self.fault_milliseconds_raw,
            1000,
        )
        self.fault_microseconds = milliseconds * 1000

        try:
            self.fault_datetime = datetime(
                self.fault_year,
                self.fault_month,
                self.fault_day,
                self.fault_hour,
                self.fault_minute,
                self.fault_seconds,
                self.fault_microseconds,
                tzinfo=timezone.utc,
            )
        except ValueError as exc:
            raise ValueError(
                "Componentes IEC invalidos en la fecha de falla: "
                f"{self.fault_year:04d}-{self.fault_month:02d}-"
                f"{self.fault_day:02d} {self.fault_hour:02d}:"
                f"{self.fault_minute:02d}:{self.fault_seconds:02d}."
                f"{milliseconds:03d}"
            ) from exc

    def _set_datetime_parts(self) -> None:
        self.fault_year = self.fault_datetime.year
        self.fault_month = self.fault_datetime.month
        self.fault_day = self.fault_datetime.day
        self.fault_hour = self.fault_datetime.hour
        self.fault_minute = self.fault_datetime.minute
        self.fault_seconds = self.fault_datetime.second
        self.fault_microseconds = self.fault_datetime.microsecond

    def _parse_fault_values(self) -> None:
        # La temporada no interviene en la estampa.
        self.fault_season = self._raw_registers[5]
        self.active_group = self._raw_registers[6]
        self.involved_phases_type = self._raw_registers[7]
        self.fault_type = self._raw_registers[8]
        self.amplitude = self._raw_registers[9]
        self.current_phase_a = self._raw_registers[10]
        self.current_phase_b = self._raw_registers[11]
        self.current_phase_c = self._raw_registers[12]
        self.earth_current = self._raw_registers[13]
        self.recognized = bool(self._raw_registers[14])

    def __repr__(self) -> str:
        return (
            f"RegistroFalla(Numero={self.fault_number}, "
            f"Fecha={self.fault_datetime.isoformat()}, "
            f"Tipo={self.fault_type}, Fases={self.involved_phases_type}, "
            f"IA={self.current_phase_a}, IB={self.current_phase_b}, "
            f"IC={self.current_phase_c}, ITierra={self.earth_current}, "
            f"Reconocida={self.recognized})"
        )

    def to_dict(self) -> dict:
        return {
            "fault_number": self.fault_number,
            "timestamp_format": self.timestamp_format,
            "fault_milliseconds_raw": self.fault_milliseconds_raw,
            "fault_datetime": self.fault_datetime.isoformat(),
            "fault_year": self.fault_year,
            "fault_month": self.fault_month,
            "fault_day": self.fault_day,
            "fault_hour": self.fault_hour,
            "fault_minute": self.fault_minute,
            "fault_seconds": self.fault_seconds,
            "fault_microseconds": self.fault_microseconds,
            "season": self.fault_season,
            "active_group": self.active_group,
            "involved_phases_type": self.involved_phases_type,
            "fault_type": self.fault_type,
            "amplitude": self.amplitude,
            "current_phase_a": self.current_phase_a,
            "current_phase_b": self.current_phase_b,
            "current_phase_c": self.current_phase_c,
            "earth_current": self.earth_current,
            "recognized": self.recognized,
        }
