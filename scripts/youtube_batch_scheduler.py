#!/usr/bin/env python3
"""Guarded uploader for the reviewed Kuchu Puchu batch 01 manifest.

The default mode is preflight only. Uploading/scheduling requires an explicit
GitHub Actions approval input. The ledger is committed after every confirmed
upload so interrupted retries can reconcile rather than duplicate.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import dropbox
from dropbox.exceptions import ApiError, AuthError
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

CHANNEL_ID = "UC2o03v6Yedd--xJRrtDs8HA"
DROPBOX_FOLDER = "/kuchu puchu tap karo_"
IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc
EXPECTED = [
    "3945279031163553286.mp4",
    "3945421511652526414.mp4",
    "3945848933751759524.mp4",
    "3946145312081982484.mp4",
    "3946233532380903412.mp4",
    "3946724574816291720.mp4",
    "3946870532124348684.mp4",
    "3947285254492037649.mp4",
    "3947457143874700364.mp4",
    "3947697853680677025.mp4",
]
MANIFEST = Path(os.environ.get("BATCH_CSV", "batch/batch-01.csv"))
LEDGER = Path(os.environ.get("LEDGER_FILE", "state/batch-01-ledger.json"))
VIDEO_DIR = Path("work/videos")
MAX_TITLE = 100
UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
READ_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required setting {name} is missing.")
    return value


def load_manifest() -> list[dict]:
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 10:
        raise RuntimeError("Batch manifest must contain exactly 10 rows.")
    if [r.get("filename", "") for r in rows] != EXPECTED:
        raise RuntimeError("Manifest filename/order does not match the reviewed batch.")
    seen_times: set[str] = set()
    for index, row in enumerate(rows):
        if row.get("batch_order") != str(index + 1):
            raise RuntimeError("Manifest batch order is invalid.")
        if not row.get("title", "").strip() or len(row["title"]) > MAX_TITLE:
            raise RuntimeError(f"Invalid or overlong title for {row['filename']}.")
        if not row.get("description", "").strip():
            raise RuntimeError(f"Description is missing for {row['filename']}.")
        if not row.get("tags", "").strip():
            raise RuntimeError(f"Tags are missing for {row['filename']}.")
        dt = datetime.fromisoformat(row["proposed_scheduled_at_ist"])
        if dt.tzinfo is None or dt.astimezone(IST).hour != 19 or dt.astimezone(IST).minute != 0:
            raise RuntimeError(f"Schedule time is not 7:00 PM IST for {row['filename']}.")
        if dt.date() != datetime(2026, 11, 12, tzinfo=IST).date() + timedelta(days=index):
            raise RuntimeError("The batch schedule is not daily from November 12, 2026.")
        stamp = dt.astimezone(UTC).isoformat()
        if stamp in seen_times:
            raise RuntimeError("Duplicate schedule time in batch.")
        seen_times.add(stamp)
        if dt.astimezone(UTC) <= datetime.now(UTC):
            raise RuntimeError(f"Scheduled time for {row['filename']} is no longer in the future.")
        row["scheduled_utc"] = dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
        row["tag_list"] = [tag.strip() for tag in row["tags"].split(",") if tag.strip()]
    return rows


def read_ledger() -> dict:
    if not LEDGER.exists():
        return {"channel_id": CHANNEL_ID, "items": {}}
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Upload ledger is unreadable; refusing to proceed.") from exc
    if data.get("channel_id") != CHANNEL_ID or not isinstance(data.get("items"), dict):
        raise RuntimeError("Ledger channel identity or structure is invalid.")
    return data


def save_ledger(data: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.parent.joinpath(".gitkeep").touch(exist_ok=True)
    LEDGER.parent.joinpath("batch-01-ledger.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_dropbox():
    try:
        return dropbox.Dropbox(
            oauth2_refresh_token=need("DROPBOX_REFRESH_TOKEN"),
            app_key=need("DROPBOX_APP_KEY"),
        )
    except Exception as exc:
        raise RuntimeError("Could not initialize Dropbox access from GitHub secrets.") from exc


def download_sources(rows: list[dict]) -> dict[str, Path]:
    dbx = build_dropbox()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for row in rows:
        filename = row["filename"]
        remote = f"{DROPBOX_FOLDER}/{filename}"
        dest = VIDEO_DIR / filename
        try:
            metadata, response = dbx.files_download(remote)
            if not isinstance(metadata, dropbox.files.FileMetadata) or metadata.size <= 0:
                raise RuntimeError(f"Dropbox item is not a non-empty file: {filename}.")
            with dest.open("wb") as out:
                total = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
                        total += len(chunk)
            if total != metadata.size:
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"Dropbox size check failed for {filename}.")
        except (AuthError, ApiError) as exc:
            raise RuntimeError(f"Dropbox access/download failed for {filename}; no YouTube call was made.") from exc
        paths[filename] = dest
        print(f"Dropbox source verified: {filename} ({dest.stat().st_size} bytes)")
    return paths


def youtube_client():
    credentials = Credentials(
        token=None,
        refresh_token=need("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=need("YOUTUBE_CLIENT_ID"),
        client_secret=need("YOUTUBE_CLIENT_SECRET"),
        scopes=UPLOAD_SCOPES + READ_SCOPES,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError("YouTube OAuth refresh failed; no upload was attempted.") from exc
    granted = set(credentials.granted_scopes or [])
    if not set(UPLOAD_SCOPES + READ_SCOPES).issubset(granted):
        raise RuntimeError("YouTube token lacks upload or readback scopes.")
    yt = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    try:
        result = yt.channels().list(part="id,snippet", mine=True).execute()
    except HttpError as exc:
        raise RuntimeError("Could not verify authorized YouTube channel.") from exc
    items = result.get("items", [])
    if len(items) != 1 or items[0].get("id") != CHANNEL_ID:
        raise RuntimeError("Authorized channel ID did not match the approved Kuchu Puchu channel.")
    print(f"Authorized channel verified: {items[0].get('snippet', {}).get('title', 'Kuchu Puchu')} ({CHANNEL_ID})")
    return yt


def scheduled_status(row: dict) -> dict:
    # Scheduled public publication is represented by privacyStatus=private plus
    # publishAt. YouTube makes the video public automatically at publishAt.
    return {
        "privacyStatus": "private",
        "publishAt": row["scheduled_utc"],
        "selfDeclaredMadeForKids": True,
    }


def verify_video(yt, video_id: str, row: dict) -> dict:
    try:
        result = yt.videos().list(part="id,snippet,status", id=video_id).execute()
    except HttpError as exc:
        raise RuntimeError(f"Readback failed for video {video_id}; inspect Studio before retrying.") from exc
    items = result.get("items", [])
    if len(items) != 1:
        raise RuntimeError(f"Could not read back video {video_id}; inspect Studio before retrying.")
    video = items[0]
    snippet = video.get("snippet", {})
    status = video.get("status", {})
    expected = datetime.fromisoformat(row["scheduled_utc"].replace("Z", "+00:00"))
    actual_text = status.get("publishAt")
    if snippet.get("channelId") != CHANNEL_ID or snippet.get("title") != row["title"]:
        raise RuntimeError(f"Video {video_id} readback identity/title mismatch.")
    if status.get("privacyStatus") != "private" or not actual_text:
        raise RuntimeError(f"Video {video_id} is not confirmed as a private scheduled video.")
    actual = datetime.fromisoformat(actual_text.replace("Z", "+00:00"))
    if abs((actual - expected).total_seconds()) > 60:
        raise RuntimeError(f"Video {video_id} publish time differs from manifest.")
    return {"video_id": video_id, "upload_status": "scheduled_verified",
            "privacy_status": status["privacyStatus"], "publish_at_utc": actual_text,
            "channel_id": snippet["channelId"], "verified_at_utc": datetime.now(UTC).isoformat()}


def run() -> None:
    mode = need("RUN_MODE").lower()
    if mode not in {"preflight", "schedule"}:
        raise RuntimeError("RUN_MODE must be preflight or schedule.")
    if mode == "schedule" and need("APPROVE_PUBLIC_SCHEDULING") != "APPROVE FIRST BATCH PUBLIC SCHEDULE":
        raise RuntimeError("Explicit public-scheduling approval phrase is required.")
    rows = load_manifest()
    ledger = read_ledger()
    for item in rows:
        prior = ledger["items"].get(item["filename"], {})
        if prior.get("video_id") or prior.get("upload_status") in {"uploading", "uncertain"}:
            raise RuntimeError(f"{item['filename']} is already recorded or uncertain; reconcile before retry.")
    paths = download_sources(rows)
    yt = youtube_client()
    print("Batch preflight passed: 10 Dropbox files, metadata, dates, OAuth scopes, and channel verified.")
    if mode == "preflight":
        print("Preflight only. No YouTube videos were uploaded or scheduled.")
        return

    # Check all planned IDs are new before any upload, to catch a prior run whose
    # ledger was lost but which left videos in the channel.
    title_query = yt.search().list(part="id,snippet", forMine=True, type="video",
                                  maxResults=50, q="Kuchu Puchu").execute()
    known_titles = {v.get("snippet", {}).get("title") for v in title_query.get("items", [])}
    if any(row["title"] in known_titles for row in rows):
        raise RuntimeError("A batch title already exists on the channel; reconcile before uploading.")

    for row in rows:
        filename = row["filename"]
        entry = {"upload_status": "uploading", "started_at_utc": datetime.now(UTC).isoformat(),
                 "scheduled_at_utc": row["scheduled_utc"], "title": row["title"]}
        ledger["items"][filename] = entry
        save_ledger(ledger)
        body = {
            "snippet": {"title": row["title"], "description": row["description"],
                        "tags": row["tag_list"], "categoryId": "22"},
            "status": scheduled_status(row),
        }
        media = MediaFileUpload(str(paths[filename]), mimetype="video/mp4",
                                chunksize=8 * 1024 * 1024, resumable=True)
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        try:
            while response is None:
                _, response = request.next_chunk()
        except Exception as exc:
            entry["upload_status"] = "uncertain"
            entry["last_error_type"] = type(exc).__name__
            save_ledger(ledger)
            raise RuntimeError(f"Upload outcome uncertain for {filename}; check Studio and ledger before retry.") from exc
        video_id = response.get("id")
        if not video_id:
            entry["upload_status"] = "uncertain"
            save_ledger(ledger)
            raise RuntimeError(f"YouTube returned no ID for {filename}; check Studio before retry.")
        entry.update(verify_video(yt, video_id, row))
        entry["filename"] = filename
        save_ledger(ledger)
        print(f"Verified scheduled upload: {filename} -> {video_id} at {entry['publish_at_utc']}")

    print(f"All 10 uploads verified. Ledger saved to {LEDGER}.")


if __name__ == "__main__":
    try:
        run()
    except (RuntimeError, OSError, csv.Error, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
