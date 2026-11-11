#!/usr/bin/env python3
"""Download one explicitly selected Dropbox MP4 and upload it to YouTube privately.

This is a one-off verification helper, not a publishing queue processor. It
never chooses a filename, never schedules publishing, and refuses public
visibility. Run from the manual GitHub Actions workflow only.
"""
from __future__ import annotations

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

DROPBOX_FOLDER = "/kuchu puchu tap karo_"
UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
READONLY_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
ALLOWED_PRIVACY = {"private", "unlisted"}
MAX_TITLE_LENGTH = 100


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is missing.")
    return value


def download_one() -> None:
    filename = required_env("DROPBOX_FILENAME")
    if (
        Path(filename).name != filename
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()-]*\.mp4", filename, re.IGNORECASE)
        or filename in {".", ".."}
    ):
        raise RuntimeError("Filename must be one plain MP4 filename; paths and other extensions are refused.")

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=required_env("DROPBOX_REFRESH_TOKEN"),
        app_key=required_env("DROPBOX_APP_KEY"),
    )
    remote_path = f"{DROPBOX_FOLDER}/{filename}"
    destination = Path("work/test-video.mp4")
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        metadata, response = dbx.files_download(remote_path)
        if not isinstance(metadata, dropbox.files.FileMetadata):
            raise RuntimeError("Dropbox did not return a file for the selected path.")
        if metadata.size <= 0:
            raise RuntimeError("Selected Dropbox file is empty.")
        with destination.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
    except (AuthError, ApiError) as exc:
        raise RuntimeError("Dropbox authentication or file download failed; verify secrets and the exact filename.") from exc

    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Dropbox download completed without a usable local video.")
    print(f"Downloaded selected file {filename!r} ({destination.stat().st_size} bytes).")


def build_youtube():
    credentials = Credentials(
        token=None,
        refresh_token=required_env("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=required_env("YOUTUBE_CLIENT_ID"),
        client_secret=required_env("YOUTUBE_CLIENT_SECRET"),
        scopes=UPLOAD_SCOPES + READONLY_SCOPES,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError(
            "YouTube OAuth refresh failed. Re-authorize with both required scopes, then update the GitHub secret."
        ) from exc

    granted = set(credentials.granted_scopes or credentials.scopes or [])
    if not set(UPLOAD_SCOPES + READONLY_SCOPES).issubset(granted):
        raise RuntimeError(
            "The YouTube refresh token lacks the upload and/or channel-read scope. Re-authorize with both scopes before uploading."
        )

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    try:
        channels = youtube.channels().list(part="id,snippet", mine=True).execute()
    except HttpError as exc:
        raise RuntimeError("Could not verify the YouTube channel. No video was uploaded.") from exc
    items = channels.get("items", [])
    if len(items) != 1:
        raise RuntimeError("Expected exactly one authenticated YouTube channel; refusing upload.")
    channel = items[0]
    print(f"Verified YouTube channel: {channel.get('snippet', {}).get('title', '(title unavailable)')!r} ({channel.get('id', 'unknown ID')}).")
    return youtube, channel["id"]


def upload_one() -> None:
    privacy = required_env("YOUTUBE_PRIVACY").lower()
    if privacy not in ALLOWED_PRIVACY:
        raise RuntimeError("Visibility must be private or unlisted; public uploads are disabled.")

    title = required_env("VIDEO_TITLE")
    if len(title) > MAX_TITLE_LENGTH:
        raise RuntimeError(f"Title exceeds YouTube's {MAX_TITLE_LENGTH}-character limit.")
    description = required_env("VIDEO_DESCRIPTION")
    video_path = Path(required_env("VIDEO_FILE"))
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise RuntimeError("The downloaded test video is missing or empty.")

    youtube, channel_id = build_youtube()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    try:
        while response is None:
            _, response = request.next_chunk()
    except HttpError as exc:
        raise RuntimeError(
            "YouTube upload failed or its final status is uncertain. Check YouTube Studio before retrying to avoid duplicates."
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            "YouTube upload stopped or its final status is uncertain. Check YouTube Studio before retrying to avoid duplicates."
        ) from exc

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube did not confirm a video ID; check YouTube Studio before retrying.")
    print(f"Upload confirmed. Video ID: {video_id}")
    print(f"Verified channel ID: {channel_id}")
    print(f"Visibility requested: {privacy}")
    print("No schedule was set. Confirm visibility in YouTube Studio before sharing.")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"download", "upload"}:
        raise SystemExit("Usage: python scripts/youtube_test_upload.py [download|upload]")
    try:
        if sys.argv[1] == "download":
            download_one()
        else:
            upload_one()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
