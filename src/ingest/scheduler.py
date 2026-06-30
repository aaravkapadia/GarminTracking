"""Daily Garmin ingest job.

Pulls one day of stats from Garmin Connect, formats it exactly like main.py
(json_normalize -> drop noisy columns -> rename -> keep), and upserts a single
row into the ``daily_stats`` table. Scheduled to run once per day at 23:59 local
time.
"""

from datetime import date
import logging

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.ingest.client import get_client, fetch_daily_stats
from src.db.db import SessionLocal, init_db
from src.db.model import DailyStats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Same drop/keep rules as main.py — kept here so the job is self-contained.
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

# Clean CSV column name -> model attribute (built from the model so the two
# never drift apart).
_COL_TO_ATTR = {col.name: attr for attr, col in DailyStats.__mapper__.columns.items()}


def format_daily_stats(stats: dict) -> dict:
    """Flatten and clean a raw fetch_daily_stats() payload into one row.

    Mirrors the transformation in main.py and returns a dict keyed by the
    cleaned column names (the same headers as stats_clean.csv).
    """
    df = pd.json_normalize(stats)

    # NB: compared against c.lower() with original-case substrings, exactly as
    # main.py does — the keep list below is what actually selects the columns.
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
        elif hasattr(value, "item"):  # numpy scalar -> python scalar
            kwargs[attr] = value.item()
        else:
            kwargs[attr] = value
    return kwargs


def ingest_today() -> None:
    """Pull today's Garmin data and upsert it into the database."""
    client = get_client()
    stats = fetch_daily_stats(client)
    row = format_daily_stats(stats)
    kwargs = _to_model_kwargs(row)

    with SessionLocal() as session:
        # merge() upserts on the primary key (calendar_date), so re-running for
        # the same day updates instead of creating a duplicate.
        session.merge(DailyStats(**kwargs))
        session.commit()

    logger.info("Ingested daily stats for %s", kwargs.get("calendar_date"))


def run_once() -> None:
    """Single ingest then exit — used by the launchd daily job."""
    init_db()  # create the table if it doesn't exist yet
    ingest_today()


def main() -> None:
    init_db()  # create the table if it doesn't exist yet
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
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        main()
