"""Publish-slot planner, driven only by config (youtube.schedule). Generalized from a fixed-timezone production rule.

    now local >= immediate_after and today free  -> action "now"
    otherwise                                     -> "schedule" at long_time on the first free day (one_long_per_day)
    Short = long slot + short_after_long_min minutes.
Whether we actually set publishAt/public is decided by youtube.auto_publish; otherwise the slot is printed as a STUDIO ACTION."""
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass
class Slot:
    action: str  # "now" | "schedule"
    at: dt.datetime  # timezone-aware, UTC

    def local(self, tz: str) -> str:
        return self.at.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M %Z")


def _hm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def plan_long(sched: dict, now: dt.datetime, taken: set | None = None) -> Slot:
    tz = ZoneInfo(sched["timezone"])
    local = now.astimezone(tz)
    taken = taken or set()
    day = local.date()
    if (not sched.get("one_long_per_day", True) or day not in taken) and local.time() >= _hm(sched["immediate_after"]) \
            and local.time() < dt.time(23, 59):
        return Slot("now", now.astimezone(dt.timezone.utc))
    if local.time() >= _hm(sched["long_time"]) or (sched.get("one_long_per_day", True) and day in taken):
        day += dt.timedelta(days=1)
    while sched.get("one_long_per_day", True) and day in taken:
        day += dt.timedelta(days=1)
    at = dt.datetime.combine(day, _hm(sched["long_time"]), tzinfo=tz)
    return Slot("schedule", at.astimezone(dt.timezone.utc))


def plan_short(sched: dict, long_slot: Slot) -> Slot:
    return Slot(long_slot.action, long_slot.at + dt.timedelta(minutes=sched.get("short_after_long_min", 60)))
