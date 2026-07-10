"""
Generate Garmin Token for saved login session(bypass ip changes)
"""

import os
from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()


def main() -> None:
    client = Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"))
    client.login() 
    token = client.garth.dumps()  
    print("\nGARMIN_TOKEN_BASE64\n")
    print(token)


if __name__ == "__main__":
    main()
