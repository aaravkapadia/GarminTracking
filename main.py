import json
from src.ingest.client import get_client, fetch_daily_stats
import pandas as pd

client = get_client()
stats = fetch_daily_stats(client)
df_raw = pd.json_normalize(stats)
df_raw.to_csv("stats.csv", index=False)

df = pd.read_csv("stats.csv")
cols_to_drop = [col for col in df.columns if any(x in col.lower() for x in [
    'heartRateValues', 'heartRateValueDescriptors', 'sleepMovement',
    'sleepLevels', 'sleepStress', 'sleepHeartRate', 'sleepBodyBattery',
    'wellnessEpoch', 'bodyBatteryActivityEventList', 'sleepRestlessMoments',
    'remSleepData', 'hrvData', 'breathingDisruptionData', 'skinTempData',
    'respirationAlgorithm', 'sleepNeed', 'nextSleepNeed'
])]
df = df.drop(columns=cols_to_drop, errors='ignore')
df.columns = (df.columns
    .str.replace('stats.', '', regex=False)
    .str.replace('heart_rate.', 'hr_', regex=False)
    .str.replace('sleep.dailySleepDTO.', 'sleep_', regex=False)
    .str.replace('sleep.', 'sleep_', regex=False)
    .str.replace('sleep_sleepScores.', 'sleep_score_', regex=False)
    .str.replace('.', '_', regex=False)
)
keep = [
    'calendarDate', 'totalSteps', 'dailyStepGoal',
    'totalKilocalories', 'activeKilocalories', 'bmrKilocalories',
    'restingHeartRate', 'maxHeartRate', 'minHeartRate',
    'averageStressLevel', 'maxStressLevel',
    'bodyBatteryHighestValue', 'bodyBatteryLowestValue', 'bodyBatteryMostRecentValue',
    'moderateIntensityMinutes', 'vigorousIntensityMinutes',
    'highlyActiveSeconds', 'activeSeconds', 'sedentarySeconds', 'sleepingSeconds',
    'floorsAscended', 'floorsDescended',
    'averageSpo2', 'lowestSpo2',
    'avgWakingRespirationValue',
    'sleep_calendarDate', 'sleep_sleepTimeSeconds', 'sleep_deepSleepSeconds',
    'sleep_lightSleepSeconds', 'sleep_remSleepSeconds', 'sleep_awakeSleepSeconds',
    'sleep_avgSleepStress', 'sleep_avgHeartRate', 'sleep_awakeCount',
    'sleep_averageSpO2Value', 'sleep_lowestSpO2Value',
    'sleep_score_overall_value', 'sleep_score_overall_qualifierKey',
    'sleep_avgOvernightHrv', 'sleep_hrvStatus', 'sleep_restingHeartRate',
    'hr_restingHeartRate', 'hr_maxHeartRate', 'hr_minHeartRate',
]
keep = [c for c in keep if c in df.columns]
df_clean = df[keep]
df_clean.to_csv("stats_clean.csv", index=False)
print(df_clean.T)
print(df.head())
