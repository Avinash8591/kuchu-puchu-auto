#!/usr/bin/env python3
"""One-time local YouTube OAuth setup for the private upload test.

Writes the OAuth credentials to Downloads/youtube_token.json. Keep that file
private and copy only its refresh_token value into GitHub Actions Secrets.
Never commit or share the token or client secret.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DOWNLOADS = Path.home() / "Downloads"
matches = sorted(DOWNLOADS.glob("client_secret*.json"))

if not matches:
    raise FileNotFoundError(
        "Could not find client_secret*.json in your Downloads folder."
    )

CLIENT_SECRET_FILE = matches[0]
OUTPUT_FILE = DOWNLOADS / "youtube_token.json"
print(f"Using OAuth client file: {CLIENT_SECRET_FILE.name}")

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
credentials = flow.run_local_server(
    host="localhost",
    port=8080,
    open_browser=True,
    access_type="offline",
    prompt="consent",
)

if not credentials.refresh_token:
    raise RuntimeError(
        "Google did not return a refresh token. Do not replace the existing "
        "GitHub secret. Check OAuth consent and try again."
    )

# Persist locally only; never print the token or add this file to the repository.
OUTPUT_FILE.write_text(credentials.to_json(), encoding="utf-8")

saved = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
if not saved.get("refresh_token"):
    raise RuntimeError("The saved credentials file does not contain a refresh token.")

print("\nYouTube authorization successful.")
print("Both required scopes were requested:")
for scope in SCOPES:
    print(f" - {scope}")
print(f"Credentials saved locally to: {OUTPUT_FILE}")
print("Open that file and copy only the refresh_token value into the")
print("YOUTUBE_REFRESH_TOKEN GitHub Actions secret.")
print("Never share the file, token, or a screenshot containing the token.")
