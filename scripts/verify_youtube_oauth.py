#!/usr/bin/env python3
"""Safely validate GitHub's YouTube OAuth secrets without uploading a video."""
from __future__ import annotations

import os
import sys

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def verify() -> tuple[str, str]:
    required = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError("Missing one or more required GitHub Actions secrets.")

    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
        scopes=SCOPES,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        # Never print Google's exception text: it can contain request details.
        raise RuntimeError("Google rejected the OAuth client/refresh-token combination.") from None

    granted = set(credentials.granted_scopes or [])
    if not set(SCOPES).issubset(granted):
        raise RuntimeError("The token is missing one or more required YouTube scopes.")

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    try:
        response = youtube.channels().list(part="id,snippet", mine=True).execute()
    except HttpError:
        raise RuntimeError("OAuth refresh succeeded, but YouTube channel lookup failed.") from None

    channels = response.get("items", [])
    if len(channels) != 1:
        raise RuntimeError("Expected one authorized YouTube channel; no upload was attempted.")

    channel = channels[0]
    channel_id = str(channel.get("id", ""))
    title = str(channel.get("snippet", {}).get("title", ""))
    if not channel_id or not title:
        raise RuntimeError("YouTube returned incomplete channel identity; no upload was attempted.")
    return channel_id, title


if __name__ == "__main__":
    try:
        channel_id, title = verify()
    except RuntimeError as exc:
        print(f"OAuth verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("OAuth client/secret/refresh-token pairing: valid")
    print("Required YouTube scopes: confirmed")
    print(f"Authorized channel: {title} ({channel_id})")
    print("Upload performed: no")
