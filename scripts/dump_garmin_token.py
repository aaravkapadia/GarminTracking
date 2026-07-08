"""Generate the GARMIN_TOKEN_BASE64 value for a headless (Railway) deploy.

Garmin usually requires MFA on first login from a new IP — which you can't
answer inside a container. So log in *once* locally with this script (answer
any MFA prompt here), then copy the printed string into Railway as the
GARMIN_TOKEN_BASE64 env var. ``src.ingest.client.get_client()`` loads it instead
of doing a password login, so the server never hits an MFA prompt.

The tokens are long-lived (garth refreshes the OAuth2 token automatically), but
regenerate and re-set the env var if Garmin ever invalidates them.

    .venv/bin/python scripts/dump_garmin_token.py
"""

import os

from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()


def main() -> None:
    client = Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"))
    client.login()  # may prompt for MFA on first run — that's expected here
    token = client.garth.dumps()  # base64 string, safe to store in an env var
    print("\n=== Set this as GARMIN_TOKEN_BASE64 in Railway ===\n")
    print(token)


if __name__ == "__main__":
    main()
