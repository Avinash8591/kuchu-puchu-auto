"""Manually reviewed, private-only Dropbox to YouTube test upload."""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import dropbox
from dropbox.exceptions import ApiError, AuthError
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from queue_scheduler.cloud_state import StateConflict, transition

FOLDER = "/kuchu puchu tap karo_"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required setting {name} is missing.")
    return value


def validate_filename(filename: str) -> str:
    if (Path(filename).name != filename or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()-]*\.mp4", filename, re.I)
            or filename.casefold() in {"001.mp4", "3932954021832974372.mp4"}):
        raise RuntimeError("Choose an eligible plain MP4 filename; paths and previously excluded files are refused.")
    return filename


def download(filename: str, destination: Path) -> None:
    dbx = dropbox.Dropbox(oauth2_refresh_token=env("DROPBOX_REFRESH_TOKEN"), app_key=env("DROPBOX_APP_KEY"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        metadata, response = dbx.files_download(f"{FOLDER}/{filename}")
        if not isinstance(metadata, dropbox.files.FileMetadata) or metadata.size <= 0:
            raise RuntimeError("Dropbox did not return a non-empty file.")
        total = 0
        with destination.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
                    total += len(chunk)
        if total != metadata.size:
            destination.unlink(missing_ok=True)
            raise RuntimeError("Downloaded size did not match Dropbox metadata.")
    except (AuthError, ApiError) as exc:
        raise RuntimeError("Dropbox download failed; verify the existing secret configuration and selected filename.") from exc


def youtube_client():
    credentials = Credentials(None, refresh_token=env("YOUTUBE_REFRESH_TOKEN"),
                              token_uri="https://oauth2.googleapis.com/token", client_id=env("YOUTUBE_CLIENT_ID"),
                              client_secret=env("YOUTUBE_CLIENT_SECRET"), scopes=SCOPES)
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError("YouTube OAuth refresh failed; no upload was attempted.") from exc
    if not set(SCOPES).issubset(set(credentials.granted_scopes or [])):
        raise RuntimeError("Required YouTube upload and read-only scopes were not confirmed; no upload was attempted.")
    api = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    try:
        channels = api.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    except HttpError as exc:
        raise RuntimeError("Could not verify authenticated YouTube channel; no upload was attempted.") from exc
    if len(channels) != 1:
        raise RuntimeError("Expected one authenticated channel; no upload was attempted.")
    return api, channels[0]


def already_uploaded(api, channel_id: str, title: str) -> None:
    try:
        result = api.search().list(part="id", forMine=True, type="video", maxResults=50, q=title).execute()
        for item in result.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                found = api.videos().list(part="snippet,status", id=vid).execute().get("items", [])
                if found and found[0].get("snippet", {}).get("channelId") == channel_id and found[0].get("snippet", {}).get("title") == title:
                    raise StateConflict("An exact-title video already exists on this channel; reserved item stays blocked for manual reconciliation.")
    except HttpError as exc:
        raise RuntimeError("YouTube duplicate check failed; refusing upload.") from exc


def run(filename: str, title: str, description: str):
    filename = validate_filename(filename)
    title, description = title.strip(), description.strip()
    if not title or len(title) > 100 or not description:
        raise RuntimeError("Provide human-reviewed, non-empty title and description (title maximum 100 characters).")
    if re.fullmatch(r"\d+", title) or re.fullmatch(r"\d+", Path(filename).stem):
        raise RuntimeError("Numeric-only titles are refused. Enter metadata reviewed against the actual video content.")

    # Reservation is written before network actions. Any later failure remains reserved,
    # which blocks automatic retry until a person reconciles the outcome.
    transition(filename, "reserve")
    video_path = Path("work/private-test-video.mp4")
    try:
        try:
            download(filename, video_path)
            api, channel = youtube_client()
            already_uploaded(api, channel["id"], title)
            body = {"snippet": {"title": title, "description": description, "categoryId": "22"},
                    "status": {"privacyStatus": "private"}}
            request = api.videos().insert(part="snippet,status", body=body,
                                          media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True))
            response = None
            try:
                while response is None:
                    _, response = request.next_chunk()
            except Exception as exc:
                raise RuntimeError("Upload outcome is uncertain; item remains reserved. Check YouTube Studio before any retry.") from exc
            video_id = response.get("id")
            if not video_id:
                raise RuntimeError("No video ID confirmed; item remains reserved. Check YouTube Studio before any retry.")
            transition(filename, "complete", video_id)
            print(f"Private upload confirmed for reviewed filename {filename!r}; video ID {video_id}.")
            print("No schedule was set. Verify visibility in YouTube Studio before considering any separate next step.")
        except Exception:
            # Preserve the reservation as the durable fail-closed lock; never reset it automatically.
            raise
    finally:
        video_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    args = parser.parse_args()
    try:
        run(args.filename, args.title, args.description)
    except (RuntimeError, StateConflict, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
