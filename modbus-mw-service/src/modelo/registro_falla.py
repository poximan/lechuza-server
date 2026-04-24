from datetime import datetime
from typing import Optional
from logosaurio import Logosaurio
from src.utils import timebox

class RegistroFalla:
    """
    Representa un registro de falla decodificado de una lectura Modbus de un rele,
    siguiendo el formato de fecha/hora IEC 870.
    """
    def __init__(self, raw_registers: list[int], logger: Logosaurio):
        """
        Inicializa una instancia de RegistroFalla con los registros Modbus brutos.

        Args:
            raw_registers (list[int]): Una lista de 15 enteros (palabras Modbus)
                                         leidos directamente del rele.
            logger (Logosaurio): Una instancia del servicio de logging.
        Raises:
            ValueError: Si la lista de registros no tiene la longitud esperada (15).
        """
        if len(raw_registers) != 15:
            raise ValueError(
                f"Se esperaban 15 registros Modbus, pero se recibieron {len(raw_registers)}."
            )
        
        self.logger = logger
        self._raw_registers = raw_registers
        self._parse_registers()

    def _parse_registers(self):
        """
        Decodifica los registros Modbus brutos en atributos significativos.
        """
        self.fault_number: int = self._raw_registers[0]

        word_0800 = self._raw_registers[1]
        word_0801 = self._raw_registers[2]
        word_0802 = self._raw_registers[3]
        word_0803 = self._raw_registers[4]

        self._parse_year(word_0800)
        self._parse_date_components(word_0801)
        self._parse_time_components(word_0802)
        self._parse_milliseconds(word_0803)

        self._validate_and_create_datetime()
        self._parse_remaining_registers()

    def _parse_year(self, word: int):
        """Decodifica el aÃ±o de la palabra Modbus 0x0800."""
        year_hi_byte = (word >> 8) & 0xFF
        year_lo_byte = word & 0xFF
        
        self.fault_year: Optional[int] = None
        if 94 <= year_hi_byte <= 99:
            self.fault_year = 1900 + year_hi_byte
        elif 0 <= (year_lo_byte & 0x7F) <= 93:
            self.fault_year = 2000 + (year_lo_byte & 0x7F)
        else:
            self.logger.log(
                f"Formato de aÃ±o no reconocido en Word 0x0800 ({word}).",
                origin="MODELO"
            )

    def _parse_date_components(self, word: int):
        """Decodifica mes, dia de la semana y dia del mes de 0x0801."""
        self.fault_month: int = ((word >> 8) & 0x0F)
        day_byte_lo = word & 0xFF
        self.fault_day_of_week: int = ((day_byte_lo & 0xE0) >> 5)
        self.fault_day: int = (day_byte_lo & 0x1F)

    def _parse_time_components(self, word: int):
        """Decodifica temporada, hora, validez de fecha y minuto de 0x0802."""
        season_hour_byte_hi = (word >> 8) & 0xFF
        self.fault_season: int = ((season_hour_byte_hi & 0x80) >> 7)
        self.fault_hour: int = (season_hour_byte_hi & 0x1F)
        
        validity_minute_byte_lo = word & 0xFF
        self.fault_date_validity: int = ((validity_minute_byte_lo & 0x80) >> 7)
        self.fault_minute: int = (validity_minute_byte_lo & 0x3F)

    def _parse_milliseconds(self, word: int):
        """Decodifica milisegundos de 0x0803 y los convierte a segundos y microsegundos."""
        self.fault_milliseconds_raw: int = word
        self.fault_seconds: int = self.fault_milliseconds_raw // 1000
        self.fault_microseconds: int = (self.fault_milliseconds_raw % 1000) * 1000

    def _validate_and_create_datetime(self):
        """Valida los componentes de fecha y crea el objeto datetime."""
        validations = [
            (self.fault_year, "AÃ±o", 1994, 2093),
            (self.fault_month, "Mes", 1, 12),
            (self.fault_day, "Dia del mes", 1, 31),
            (self.fault_day_of_week, "Dia de la semana", 1, 7),
            (self.fault_season, "Temporada", 0, 1),
            (self.fault_hour, "Hora", 0, 23),
            (self.fault_minute, "Minuto", 0, 59),
            (self.fault_date_validity, "Validez de fecha", 0, 1),
            (self.fault_seconds, "Segundos", 0, 59),
            (self.fault_microseconds, "Microsegundos", 0, 999999),
        ]

        is_date_components_valid = True
        for value, name, min_val, max_val in validations:
            if value is not None and not (min_val <= value <= max_val):
                self.logger.log(
                    f"{name} fuera de rango ({min_val}-{max_val}): {value}",
                    origin="MODELO"
                )
                is_date_components_valid = False

        self.fault_datetime: Optional[datetime] = None
        if not is_date_components_valid or self.fault_year is None:
            self.logger.log(
                "Componentes de fecha/hora invalidos. No se creara el objeto datetime.",
                origin="MODELO"
            )
            return

        try:
            naive_dt = datetime(
                self.fault_year,
                self.fault_month,
                self.fault_day,
                self.fault_hour,
                self.fault_minute,
                self.fault_seconds,
                self.fault_microseconds
            )
            self.fault_datetime = timebox.parse(naive_dt, legacy=True)
        except ValueError as e:
            self.logger.log(
                f"Error al crear datetime: {e}. Valores: AÃ±o={self.fault_year}, Mes={self.fault_month}, "
                f"Dia={self.fault_day}, Hora={self.fault_hour}, Minuto={self.fault_minute}, "
                f"Segundo={self.fault_seconds}, Microsegundo={self.fault_microseconds}",
                origin="MODELO"
            )
    
    def _parse_remaining_registers(self):
        """Decodifica el resto de los registros de falla."""
        # Se usa un diccionario para asignar nombres a los indices, mejorando la legibilidad.
        self.ignored_word_6: int = self._raw_registers[5]
        self.active_group: int = self._raw_registers[6]
        self.involved_phases_type: int = self._raw_registers[7]
        self.fault_type: int = self._raw_registers[8]
        self.amplitude: int = self._raw_registers[9]
        self.current_phase_a: int = self._raw_registers[10]
        self.current_phase_b: int = self._raw_registers[11]
        self.current_phase_c: int = self._raw_registers[12]
        self.earth_current: int = self._raw_registers[13]
        self.recognized: bool = bool(self._raw_registers[14])

    def __repr__(self) -> str:
        """Representacion para depuracion."""
        date_str = self.fault_datetime.isoformat() if self.fault_datetime else "N/A"
        return (f"RegistroFalla(Numero={self.fault_number}, Fecha={date_str}, "
                f"Tipo={self.fault_type}, Fases={self.involved_phases_type}, "
                f"IA={self.current_phase_a}, IB={self.current_phase_b}, IC={self.current_phase_c}, "
                f"ITierra={self.earth_current}, Reconocida={self.recognized})")

    def to_dict(self) -> dict:
        """Exporta los datos de la falla a un diccionario."""
        return {
            "fault_number": self.fault_number,
            "fault_year": self.fault_year,
            "fault_month": self.fault_month,
            "fault_day": self.fault_day,
            "fault_hour": self.fault_hour,
            "fault_minute": self.fault_minute,
            "fault_seconds": self.fault_seconds,
            "fault_microseconds": self.fault_microseconds,
            "fault_milliseconds_raw": self.fault_milliseconds_raw,
            "fault_datetime": self.fault_datetime.isoformat() if self.fault_datetime else None,
            "day_of_week": self.fault_day_of_week,
            "season": self.fault_season,
            "date_validity": self.fault_date_validity,
            "ignored_word_6": self.ignored_word_6,
            "active_group": self.active_group,
            "involved_phases_type": self.involved_phases_type,
            "fault_type": self.fault_type,
            "amplitude": self.amplitude,
            "current_phase_a": self.current_phase_a,
            "current_phase_b": self.current_phase_b,
            "current_phase_c": self.current_phase_c,
            "earth_current": self.earth_current,
            "recognized": self.recognized
        }
