#!/usr/bin/env python3
"""One-time local YouTube OAuth setup for the upload test workflow.

The resulting refresh token must be stored directly in GitHub Actions Secrets.
Never commit or share the token or client secret.
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DOWNLOADS = Path.home() / "Downloads"
matches = list(DOWNLOADS.glob("client_secret*.json"))

if not matches:
    raise FileNotFoundError(
        "Could not find client_secret*.json in your Downloads folder."
    )

CLIENT_SECRET_FILE = matches[0]
print(f"Using credentials: {CLIENT_SECRET_FILE.name}")

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
credentials = flow.run_local_server(
    host="localhost",
    port=8080,
    open_browser=True,
    access_type="offline",
    prompt="consent",
)

print("\nYouTube authorization successful!")
print("Refresh token received:", bool(credentials.refresh_token))
print("Save the refresh token directly as the YOUTUBE_REFRESH_TOKEN GitHub secret.")
print("Do not send it in chat, commit it, or share a screenshot containing it.")
