import os
from datetime import date
from garminconnect import Garmin
from dotenv import load_dotenv

load_dotenv()

def get_client() -> Garmin:
    """Return a logged-in Garmin client.

    Prefers pre-generated OAuth tokens in GARMIN_TOKEN_BASE64 (see
    scripts/dump_garmin_token.py) so headless deploys never hit an interactive
    MFA prompt. Falls back to email+password login for local use, which may
    prompt for MFA on first run.
    """
    token = os.getenv("GARMIN_TOKEN_BASE64")
    if token:
        client = Garmin()
        client.garth.loads(token)  # restore OAuth tokens; no password/MFA needed
        return client

    client = Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"))
    client.login()
    return client

def fetch_daily_stats(client: Garmin, target_date: str = None) -> dict:
    if target_date is None:
        target_date = date.today().isoformat()  # "2026-06-29"
    
    return {
        "stats": client.get_stats(target_date),
        "heart_rate": client.get_heart_rates(target_date),
        "sleep": client.get_sleep_data(target_date),
    }

def fetch_activities(client: Garmin, limit: int = 10) -> list:
    return client.get_activities(0, limit)