from datetime import date
from typing import Optional
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class DailyStats(Base):
    """One row per day of Garmin watch data, matching stats_clean.csv.

    ``calendar_date`` is the primary key, so re-ingesting the same day is a
    no-op/upsert rather than a duplicate row. The scheduler appends one new
    day per run.
    """

    __tablename__ = "daily_stats"

    # Primary key — one row per day.
    calendar_date: Mapped[date] = mapped_column("calendarDate", sa.Date, primary_key=True)

    # Activity / steps
    total_steps: Mapped[Optional[int]] = mapped_column("totalSteps")
    daily_step_goal: Mapped[Optional[int]] = mapped_column("dailyStepGoal")
    total_kilocalories: Mapped[Optional[float]] = mapped_column("totalKilocalories")
    active_kilocalories: Mapped[Optional[float]] = mapped_column("activeKilocalories")
    bmr_kilocalories: Mapped[Optional[float]] = mapped_column("bmrKilocalories")

    # Heart rate (from stats block)
    resting_heart_rate: Mapped[Optional[int]] = mapped_column("restingHeartRate")
    max_heart_rate: Mapped[Optional[int]] = mapped_column("maxHeartRate")
    min_heart_rate: Mapped[Optional[int]] = mapped_column("minHeartRate")

    # Stress
    average_stress_level: Mapped[Optional[int]] = mapped_column("averageStressLevel")
    max_stress_level: Mapped[Optional[int]] = mapped_column("maxStressLevel")

    # Body battery
    body_battery_highest_value: Mapped[Optional[int]] = mapped_column("bodyBatteryHighestValue")
    body_battery_lowest_value: Mapped[Optional[int]] = mapped_column("bodyBatteryLowestValue")
    body_battery_most_recent_value: Mapped[Optional[int]] = mapped_column("bodyBatteryMostRecentValue")

    # Intensity / active time
    moderate_intensity_minutes: Mapped[Optional[int]] = mapped_column("moderateIntensityMinutes")
    vigorous_intensity_minutes: Mapped[Optional[int]] = mapped_column("vigorousIntensityMinutes")
    highly_active_seconds: Mapped[Optional[int]] = mapped_column("highlyActiveSeconds")
    active_seconds: Mapped[Optional[int]] = mapped_column("activeSeconds")
    sedentary_seconds: Mapped[Optional[int]] = mapped_column("sedentarySeconds")
    sleeping_seconds: Mapped[Optional[int]] = mapped_column("sleepingSeconds")

    # Floors
    floors_ascended: Mapped[Optional[float]] = mapped_column("floorsAscended")
    floors_descended: Mapped[Optional[float]] = mapped_column("floorsDescended")

    # SpO2 / respiration (daytime)
    average_spo2: Mapped[Optional[float]] = mapped_column("averageSpo2")
    lowest_spo2: Mapped[Optional[int]] = mapped_column("lowestSpo2")
    avg_waking_respiration_value: Mapped[Optional[float]] = mapped_column("avgWakingRespirationValue")

    # Sleep
    sleep_calendar_date: Mapped[Optional[date]] = mapped_column("sleep_calendarDate", sa.Date)
    sleep_sleep_time_seconds: Mapped[Optional[int]] = mapped_column("sleep_sleepTimeSeconds")
    sleep_deep_sleep_seconds: Mapped[Optional[int]] = mapped_column("sleep_deepSleepSeconds")
    sleep_light_sleep_seconds: Mapped[Optional[int]] = mapped_column("sleep_lightSleepSeconds")
    sleep_rem_sleep_seconds: Mapped[Optional[int]] = mapped_column("sleep_remSleepSeconds")
    sleep_awake_sleep_seconds: Mapped[Optional[int]] = mapped_column("sleep_awakeSleepSeconds")
    sleep_avg_sleep_stress: Mapped[Optional[float]] = mapped_column("sleep_avgSleepStress")
    sleep_avg_heart_rate: Mapped[Optional[float]] = mapped_column("sleep_avgHeartRate")
    sleep_awake_count: Mapped[Optional[int]] = mapped_column("sleep_awakeCount")
    sleep_average_spo2_value: Mapped[Optional[float]] = mapped_column("sleep_averageSpO2Value")
    sleep_lowest_spo2_value: Mapped[Optional[int]] = mapped_column("sleep_lowestSpO2Value")
    sleep_score_overall_value: Mapped[Optional[int]] = mapped_column("sleep_score_overall_value")
    sleep_score_overall_qualifier_key: Mapped[Optional[str]] = mapped_column("sleep_score_overall_qualifierKey")
    sleep_avg_overnight_hrv: Mapped[Optional[float]] = mapped_column("sleep_avgOvernightHrv")
    sleep_hrv_status: Mapped[Optional[str]] = mapped_column("sleep_hrvStatus")
    sleep_resting_heart_rate: Mapped[Optional[int]] = mapped_column("sleep_restingHeartRate")

    # Heart rate (from heart-rate block)
    hr_resting_heart_rate: Mapped[Optional[int]] = mapped_column("hr_restingHeartRate")
    hr_max_heart_rate: Mapped[Optional[int]] = mapped_column("hr_maxHeartRate")
    hr_min_heart_rate: Mapped[Optional[int]] = mapped_column("hr_minHeartRate")

    def __repr__(self) -> str:
        return f"<DailyStats {self.calendar_date} steps={self.total_steps}>"
