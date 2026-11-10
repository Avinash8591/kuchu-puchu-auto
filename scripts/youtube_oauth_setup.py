
import json
import glob
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

DOWNLOADS = Path.home() / "Downloads"
matches = list(DOWNLOADS.glob("client_secret*.json"))

if not matches:
    raise FileNotFoundError(
        "Could not find client_secret*.json in your Downloads folder."
    )

CLIENT_SECRET_FILE = matches[0]

print(f"Using credentials: {CLIENT_SECRET_FILE.name}")

flow = InstalledAppFlow.from_client_secrets_file(
    str(CLIENT_SECRET_FILE),
    SCOPES
)

credentials = flow.run_local_server(
    host="localhost",
    port=8080,
    open_browser=True,
    access_type="offline",
    prompt="consent"
)

output_file = Path("youtube_token.json")
output_file.write_text(credentials.to_json(), encoding="utf-8")

print("\nYouTube authorization successful!")
print("Token saved to:", output_file.resolve())
print("Refresh token received:", bool(credentials.refresh_token))
