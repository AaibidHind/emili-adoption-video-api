from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent
env_path = ROOT / ".env"
load_dotenv(dotenv_path=env_path)

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

print("Using .env at:", env_path)
print("CLIENT_ID from env:", CLIENT_ID)
print("CLIENT_SECRET present:", bool(CLIENT_SECRET))

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("ERROR: YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET not set in .env")

creds_data = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
}


flow = InstalledAppFlow.from_client_config(
    creds_data,
    scopes=["https://www.googleapis.com/auth/youtube.upload"]
)

creds = flow.run_local_server(port=0, prompt="consent")

print("\nREFRESH TOKEN:\n")
print(creds.refresh_token)
print("\nPaste this into your .env as:")
print("YOUTUBE_REFRESH_TOKEN=<paste_here>")
