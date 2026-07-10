"""
Daily Garmin ingest job.
"""

from datetime import date, timedelta
import logging
import time

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.ingest.client import get_client, fetch_daily_stats
from src.db.db import SessionLocal, init_db
from src.db.model import DailyStats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DROP_SUBSTRINGS = [
    "heartRateValues", "heartRateValueDescriptors", "sleepMovement",
    "sleepLevels", "sleepStress", "sleepHeartRate", "sleepBodyBattery",
    "wellnessEpoch", "bodyBatteryActivityEventList", "sleepRestlessMoments",
    "remSleepData", "hrvData", "breathingDisruptionData", "skinTempData",
    "respirationAlgorithm", "sleepNeed", "nextSleepNeed",
]

_KEEP = [
    "calendarDate", "totalSteps", "dailyStepGoal",
    "totalKilocalories", "activeKilocalories", "bmrKilocalories",
    "restingHeartRate", "maxHeartRate", "minHeartRate",
    "averageStressLevel", "maxStressLevel",
    "bodyBatteryHighestValue", "bodyBatteryLowestValue", "bodyBatteryMostRecentValue",
    "moderateIntensityMinutes", "vigorousIntensityMinutes",
    "highlyActiveSeconds", "activeSeconds", "sedentarySeconds", "sleepingSeconds",
    "floorsAscended", "floorsDescended",
    "averageSpo2", "lowestSpo2",
    "avgWakingRespirationValue",
    "sleep_calendarDate", "sleep_sleepTimeSeconds", "sleep_deepSleepSeconds",
    "sleep_lightSleepSeconds", "sleep_remSleepSeconds", "sleep_awakeSleepSeconds",
    "sleep_avgSleepStress", "sleep_avgHeartRate", "sleep_awakeCount",
    "sleep_averageSpO2Value", "sleep_lowestSpO2Value",
    "sleep_score_overall_value", "sleep_score_overall_qualifierKey",
    "sleep_avgOvernightHrv", "sleep_hrvStatus", "sleep_restingHeartRate",
    "hr_restingHeartRate", "hr_maxHeartRate", "hr_minHeartRate",
]

_COL_TO_ATTR = {col.name: attr for attr, col in DailyStats.__mapper__.columns.items()}


def format_daily_stats(stats: dict) -> dict:
    """Flatten and clean a raw fetch_daily_stats() payload into one row."""
    df = pd.json_normalize(stats)
    drop = [c for c in df.columns if any(x in c.lower() for x in _DROP_SUBSTRINGS)]
    df = df.drop(columns=drop, errors="ignore")

    df.columns = (df.columns
        .str.replace("stats.", "", regex=False)
        .str.replace("heart_rate.", "hr_", regex=False)
        .str.replace("sleep.dailySleepDTO.", "sleep_", regex=False)
        .str.replace("sleep.", "sleep_", regex=False)
        .str.replace("sleep_sleepScores.", "sleep_score_", regex=False)
        .str.replace(".", "_", regex=False)
    )

    keep = [c for c in _KEEP if c in df.columns]
    return df[keep].iloc[0].to_dict()


def _to_model_kwargs(row: dict) -> dict:
    """Convert a cleaned row into native-Python kwargs for DailyStats."""
    kwargs = {}
    for col_name, value in row.items():
        attr = _COL_TO_ATTR.get(col_name)
        if attr is None:
            continue
        if pd.isna(value):
            kwargs[attr] = None
        elif col_name.endswith("calendarDate"):
            kwargs[attr] = date.fromisoformat(str(value)[:10])
        elif hasattr(value, "item"):  
            kwargs[attr] = value.item()
        else:
            kwargs[attr] = value
    return kwargs


def ingest_day(target_date: str = None, client=None) -> None:
    """Pull one day of Garmin data and upsert it. Defaults to today."""
    client = client or get_client()
    stats = fetch_daily_stats(client, target_date)
    row = format_daily_stats(stats)
    kwargs = _to_model_kwargs(row)

    with SessionLocal() as session:
        session.merge(DailyStats(**kwargs))
        session.commit()

    logger.info("Ingested daily stats for %s", kwargs.get("calendar_date"))


def ingest_today() -> None:
    """Pull today's Garmin data and upsert it into the database."""
    ingest_day()


def run_once(target_date: str = None) -> None:
    """Single ingest then exit, used by the launchd daily job."""
    init_db()  
    ingest_day(target_date)


def run_backfill(start: str, end: str = None, pause: float = 1.0) -> None:
    """Backfill an inclusive range of past days, authenticating once."""
    init_db()
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end) if end else date.today()
    if start_d > end_d:
        raise ValueError(f"start {start_d} is after end {end_d}")

    client = get_client() 
    day = start_d
    ok = 0
    while day <= end_d:
        try:
            ingest_day(day.isoformat(), client=client)
            ok += 1
        except Exception as e:
            logger.warning("Backfill skipped %s: %s", day, e)
        day += timedelta(days=1)
        if day <= end_d:
            time.sleep(pause)
    logger.info("Backfill complete: %d/%d days ingested (%s → %s)",
                ok, (end_d - start_d).days + 1, start_d, end_d)


def main() -> None:
    init_db() 
    scheduler = BlockingScheduler()
    scheduler.add_job(
        ingest_today,
        trigger=CronTrigger(hour=23, minute=59),
        id="garmin_daily_ingest",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    
    logger.info("Scheduler started — daily Garmin ingest at 23:59 local time. Ctrl+C to stop.")
    scheduler.start()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Garmin daily ingest")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single ingest and exit (used by the launchd daily job).",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Backfill a specific day instead of today. Implies --once.",
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="Backfill every day from this date through --end (default: today). "
             "One login for the whole range.",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        help="Last day of a --start backfill range (inclusive). Defaults to today.",
    )
    args = parser.parse_args()

    if args.start:
        run_backfill(args.start, args.end)
    elif args.date:
        run_once(args.date)
    elif args.once:
        run_once()
    else:
        main()
