from croniter import croniter
from datetime import datetime, timedelta, timezone
import pytz

def parse_cron_expr(expr, base_time=None):
    base = base_time or datetime.now(timezone.utc)
    return croniter(expr, base)

def utc_to_local(dt, tz_name='UTC'):
    tz = pytz.timezone(tz_name)
    return dt.replace(tzinfo=timezone.utc).astimezone(tz)

def humanize_timedelta(td: timedelta):
    seconds = int(td.total_seconds())
    periods = [
        ('day', 60*60*24),
        ('hour', 60*60),
        ('minute', 60),
        ('second', 1)
    ]
    strings = []
    for name, count in periods:
        value = seconds // count
        if value:
            seconds -= value * count
            strings.append(f"{value} {name}{'s' if value > 1 else ''}")
    return ', '.join(strings) or '0 seconds' 