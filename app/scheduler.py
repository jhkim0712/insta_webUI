"""APScheduler wrapper: keeps a single crawl job in sync with the saved settings."""
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .instaloader_service import run_crawl

JOB_ID = "crawl"
TZ = os.environ.get("TZ") or "UTC"
try:
    ZoneInfo(TZ)
except (ZoneInfoNotFoundError, ValueError):
    TZ = "UTC"


def local_tz() -> ZoneInfo:
    return ZoneInfo(TZ)


scheduler = BackgroundScheduler(timezone=TZ, job_defaults={"coalesce": True, "max_instances": 1})


def build_trigger(schedule: dict):
    mode = schedule.get("mode", "disabled")
    if mode == "interval":
        minutes = max(1, int(schedule.get("interval_minutes") or 60))
        return IntervalTrigger(minutes=minutes, timezone=TZ)
    if mode == "cron":
        return CronTrigger.from_crontab(schedule.get("cron", "").strip(), timezone=TZ)
    return None


def apply_schedule(schedule: dict) -> None:
    trigger = build_trigger(schedule)
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    if trigger is not None:
        scheduler.add_job(run_crawl, trigger, id=JOB_ID, kwargs={"trigger": "schedule"},
                          misfire_grace_time=600)


def next_run_time():
    job = scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None


def start(schedule: dict) -> None:
    if not scheduler.running:
        scheduler.start()
    apply_schedule(schedule)


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
