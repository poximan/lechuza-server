from datetime import datetime, timedelta
from src.modelo.registro_falla import RegistroFalla
from src.modelo.rele_micom import MicomRelayClock


def decode_disturbance_finish(
    finish_words: list[int],
    date_format: int,
) -> datetime:
    if len(finish_words) != 4:
        raise ValueError(
            "La fecha de perturbacion requiere cuatro palabras"
        )
    if date_format == RegistroFalla.DATE_FORMAT_PRIVATE:
        seconds_since_epoch = (
            finish_words[1] << 16
        ) | finish_words[0]
        milliseconds = (finish_words[3] << 16) | finish_words[2]
        if milliseconds > 999:
            raise ValueError(
                "Milisegundos privados de perturbacion fuera de rango: "
                f"{milliseconds}"
            )
        return RegistroFalla.PRIVATE_EPOCH + timedelta(
            seconds=seconds_since_epoch,
            milliseconds=milliseconds,
        )
    if date_format == RegistroFalla.DATE_FORMAT_IEC_870:
        return MicomRelayClock.from_words(
            finish_words,
            date_format,
        ).timestamp
    raise ValueError(f"Formato de fecha MiCOM desconocido: {date_format}")


