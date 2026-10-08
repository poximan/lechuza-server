import calendar
from datetime import datetime, timedelta, timezone

from timeauthority import get_time_authority

clock = get_time_authority()
LOCAL = timezone(timedelta(hours=-3))


def months_before(value: datetime, months: int) -> datetime:
    local = value.astimezone(LOCAL)
    index = local.year * 12 + local.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return local.replace(year=year, month=month,
                         day=min(local.day, calendar.monthrange(year, month)[1])).astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return clock.utc_iso_milliseconds(value)
