#!/usr/bin/env python3
"""Guarded uploader for the reviewed Kuchu Puchu batch 01 manifest."""
from __future__ import annotations

import csv
import json
import os
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
    "3945279031163553286.mp4", "3945421511652526414.mp4",
    "3945848933751759524.mp4", "3946145312081982484.mp4",
    "3946233532380903412.mp4", "3946724574816291720.mp4",
    "3946870532124348684.mp4", "3947285254492037649.mp4",
    "3947457143874700364.mp4", "3947697853680677025.mp4",
]
MANIFEST = Path(os.environ.get("BATCH_CSV", "batch/batch-01.csv"))
LEDGER = Path(os.environ.get("LEDGER_FILE", "state/batch-01-ledger.json"))
VIDEO_DIR = Path("work/videos")
UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
READ_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required setting {name} is missing.")
    return value


def load_manifest() -> list[dict]:
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 10 or [r.get("filename") for r in rows] != EXPECTED:
        raise RuntimeError("Manifest must contain the exact reviewed 10-file batch in order.")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if row.get("batch_order") != str(i + 1):
            raise RuntimeError("Batch order is invalid.")
        title = row.get("title", "").strip()
        if not title or len(title) > 100:
            raise RuntimeError(f"Missing or overlong title for {row['filename']}.")
        if not row.get("description", "").strip() or not row.get("tags", "").strip():
            raise RuntimeError(f"Description or tags are missing for {row['filename']}.")
        dt = datetime.fromisoformat(row["proposed_scheduled_at_ist"])
        if dt.tzinfo is None:
            raise RuntimeError("Schedule entries must include an explicit timezone.")
        local = dt.astimezone(IST)
        if (local.hour, local.minute, local.second) != (19, 0, 0):
            raise RuntimeError("Every schedule must be at 7:00 PM IST.")
        if local.date() != datetime(2026, 11, 12, tzinfo=IST).date() + timedelta(days=i):
            raise RuntimeError("Schedule must be daily starting November 12, 2026.")
        if dt.astimezone(UTC) <= datetime.now(UTC):
            raise RuntimeError(f"Schedule time has passed for {row['filename']}.")
        key = dt.astimezone(UTC).isoformat()
        if key in seen:
            raise RuntimeError("Duplicate scheduled timestamp.")
        seen.add(key)
        row["scheduled_utc"] = dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
        row["tag_list"] = [x.strip() for x in row["tags"].split(",") if x.strip()]
    return rows


def load_ledger() -> dict:
    if not LEDGER.exists():
        return {"channel_id": CHANNEL_ID, "items": {}}
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Upload ledger is unreadable; refusing to retry.") from exc
    if data.get("channel_id") != CHANNEL_ID or not isinstance(data.get("items"), dict):
        raise RuntimeError("Upload ledger channel or structure is invalid.")
    return data


def save_ledger(data: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=LEDGER.name + ".", dir=str(LEDGER.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, LEDGER)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def dropbox_client():
    try:
        return dropbox.Dropbox(oauth2_refresh_token=required("DROPBOX_REFRESH_TOKEN"),
                               app_key=required("DROPBOX_APP_KEY"))
    except Exception as exc:
        raise RuntimeError("Could not initialize Dropbox access from GitHub secrets.") from exc


def download_sources(rows: list[dict]) -> dict[str, Path]:
    dbx = dropbox_client()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for row in rows:
        name = row["filename"]
        try:
            meta, response = dbx.files_download(f"{DROPBOX_FOLDER}/{name}")
            if not isinstance(meta, dropbox.files.FileMetadata) or meta.size <= 0:
                raise RuntimeError(f"Dropbox did not return a non-empty MP4 for {name}.")
            target = VIDEO_DIR / name
            total = 0
            with target.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
                        total += len(chunk)
            if total != meta.size:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"Dropbox download size did not match for {name}.")
            paths[name] = target
            print(f"Dropbox file verified: {name} ({total} bytes)")
        except (AuthError, ApiError) as exc:
            raise RuntimeError(f"Dropbox access failed for {name}; YouTube upload was not attempted.") from exc
    return paths


def youtube_client():
    creds = Credentials(
        token=None, refresh_token=required("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=required("YOUTUBE_CLIENT_ID"), client_secret=required("YOUTUBE_CLIENT_SECRET"),
        scopes=UPLOAD_SCOPES + READ_SCOPES,
    )
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError("YouTube OAuth refresh failed.") from exc
    if not set(UPLOAD_SCOPES + READ_SCOPES).issubset(set(creds.granted_scopes or [])):
        raise RuntimeError("YouTube token lacks required upload/readback scopes.")
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        channels = yt.channels().list(part="id,snippet,contentDetails", mine=True).execute().get("items", [])
    except HttpError as exc:
        raise RuntimeError("Unable to verify authorized YouTube channel.") from exc
    if len(channels) != 1 or channels[0].get("id") != CHANNEL_ID:
        raise RuntimeError("OAuth token is not authorized for the confirmed Kuchu Puchu channel.")
    print(f"Authorized channel verified: {channels[0].get('snippet', {}).get('title', 'Kuchu Puchu')} ({CHANNEL_ID})")
    return yt, channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def check_schedule_collisions(yt, uploads_playlist: str, rows: list[dict]) -> None:
    # The published batch CSV already reports conflicts with master rows 1–10.
    # This hard stop remains until a reviewed manifest resolves those conflicts.
    if any("Conflicts with master schedule row" in r.get("review_notes", "") for r in rows):
        raise RuntimeError("Manifest still conflicts with master schedule rows 1–10; update and review it before upload.")
    ids, token = [], None
    try:
        while True:
            page = yt.playlistItems().list(part="contentDetails", playlistId=uploads_playlist,
                                           maxResults=50, pageToken=token).execute()
            ids.extend(x["contentDetails"]["videoId"] for x in page.get("items", []))
            token = page.get("nextPageToken")
            if not token:
                break
        for offset in range(0, len(ids), 50):
            result = yt.videos().list(part="status", id=",".join(ids[offset:offset + 50])).execute()
            for video in result.get("items", []):
                publish = video.get("status", {}).get("publishAt")
                if not publish:
                    continue
                actual = datetime.fromisoformat(publish.replace("Z", "+00:00"))
                for row in rows:
                    wanted = datetime.fromisoformat(row["scheduled_utc"].replace("Z", "+00:00"))
                    if abs((actual - wanted).total_seconds()) < 60:
                        raise RuntimeError(f"Channel already has a video scheduled for {wanted.astimezone(IST).isoformat()}.")
    except HttpError as exc:
        raise RuntimeError("Could not read existing scheduled videos; refusing upload.") from exc


def verify_video(yt, video_id: str, row: dict) -> dict:
    try:
        items = yt.videos().list(part="id,snippet,status", id=video_id).execute().get("items", [])
    except HttpError as exc:
        raise RuntimeError(f"Readback failed for {video_id}; reconcile in Studio before retry.") from exc
    if len(items) != 1:
        raise RuntimeError(f"Readback missing for {video_id}; reconcile in Studio before retry.")
    video = items[0]
    snippet, status = video.get("snippet", {}), video.get("status", {})
    expected = datetime.fromisoformat(row["scheduled_utc"].replace("Z", "+00:00"))
    text = status.get("publishAt")
    if snippet.get("channelId") != CHANNEL_ID or snippet.get("title") != row["title"]:
        raise RuntimeError(f"Channel/title verification failed for {video_id}.")
    if status.get("privacyStatus") != "private" or not text:
        raise RuntimeError(f"Scheduled private status not confirmed for {video_id}.")
    actual = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if abs((actual - expected).total_seconds()) > 60:
        raise RuntimeError(f"Scheduled time verification failed for {video_id}.")
    return {"video_id": video_id, "upload_status": "scheduled_verified",
            "privacy_status": "private", "publish_at_utc": text,
            "channel_id": CHANNEL_ID, "verified_at_utc": datetime.now(UTC).isoformat()}


def main():
    mode = required("RUN_MODE").lower()
    if mode not in {"preflight", "schedule"}:
        raise RuntimeError("RUN_MODE must be preflight or schedule.")
    if mode == "schedule" and required("APPROVE_PUBLIC_SCHEDULING") != "APPROVE FIRST BATCH PUBLIC SCHEDULE":
        raise RuntimeError("Exact public-scheduling approval phrase is required.")
    rows = load_manifest()
    ledger = load_ledger()
    for row in rows:
        state = ledger["items"].get(row["filename"], {})
        if state.get("video_id") or state.get("upload_status") in {"uploading", "uncertain"}:
            raise RuntimeError(f"{row['filename']} exists in ledger; reconcile before retry.")
    files = download_sources(rows)
    yt, playlist = youtube_client()
    check_schedule_collisions(yt, playlist, rows)
    print("Preflight passed: files, metadata, dates, OAuth channel/scopes, schedule checks.")
    if mode == "preflight":
        print("Preflight only; no YouTube videos were uploaded or scheduled.")
        return

    for row in rows:
        name = row["filename"]
        entry = {"upload_status": "uploading", "started_at_utc": datetime.now(UTC).isoformat(),
                 "scheduled_at_utc": row["scheduled_utc"], "title": row["title"]}
        ledger["items"][name] = entry
        save_ledger(ledger)
        body = {
            "snippet": {"title": row["title"], "description": row["description"],
                        "tags": row["tag_list"], "categoryId": "22"},
            "status": {"privacyStatus": "private", "publishAt": row["scheduled_utc"],
                       "selfDeclaredMadeForKids": True},
        }
        request = yt.videos().insert(
            part="snippet,status", body=body,
            media_body=MediaFileUpload(str(files[name]), mimetype="video/mp4",
                                       chunksize=8 * 1024 * 1024, resumable=True),
        )
        response = None
        try:
            while response is None:
                _, response = request.next_chunk()
        except Exception as exc:
            entry["upload_status"] = "uncertain"
            entry["last_error_type"] = type(exc).__name__
            save_ledger(ledger)
            raise RuntimeError(f"Upload outcome uncertain for {name}; inspect Studio before retry.") from exc
        video_id = response.get("id")
        if not video_id:
            entry["upload_status"] = "uncertain"
            save_ledger(ledger)
            raise RuntimeError(f"No YouTube ID for {name}; inspect Studio before retry.")
        entry["video_id"] = video_id
        save_ledger(ledger)
        entry.update(verify_video(yt, video_id, row))
        entry["filename"] = name
        save_ledger(ledger)
        print(f"Verified: {name} -> {video_id} at {entry['publish_at_utc']}")
    print("All ten uploads confirmed as private scheduled videos.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, csv.Error, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
