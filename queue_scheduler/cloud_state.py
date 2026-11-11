"""Cloud-persistent queue state through GitHub repository Contents API.

The Actions workflow serializes runs and this module makes every write conditional
on the previously read blob SHA. Failed or uncertain reservations remain blocked.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
STATE_PATH = "queue-state/state.json"


class StateConflict(RuntimeError):
    pass


def _request(url: str, token: str, method: str = "GET", body: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kuchu-puchu-private-queue",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        if exc.code == 409:
            raise StateConflict("Cloud queue state changed concurrently; rerun after reviewing state.") from exc
        raise RuntimeError(f"GitHub state request failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("GitHub state request failed; reservation outcome may be uncertain.") from exc


def _config():
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    branch = os.environ.get("STATE_BRANCH", "main").strip()
    if not repo or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required.")
    return repo, token, branch


def read():
    repo, token, branch = _config()
    path = urllib.parse.quote(STATE_PATH, safe="/")
    url = f"{API}/repos/{repo}/contents/{path}?ref={urllib.parse.quote(branch, safe='')}"
    status, result = _request(url, token)
    if status == 404:
        return {"schema_version": 1, "items": {}}, None
    try:
        raw = base64.b64decode(result["content"]).decode("utf-8")
        state = json.loads(raw)
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("Cloud queue state is malformed; refusing to continue.") from exc
    if state.get("schema_version") != 1 or not isinstance(state.get("items"), dict):
        raise RuntimeError("Cloud queue state schema is unsupported; refusing to continue.")
    return state, result.get("sha")


def write(state, expected_sha):
    repo, token, branch = _config()
    path = urllib.parse.quote(STATE_PATH, safe="/")
    url = f"{API}/repos/{repo}/contents/{path}"
    body = {
        "message": "Update private YouTube queue state",
        "content": base64.b64encode((json.dumps(state, indent=2, sort_keys=True) + "\n").encode()).decode(),
        "branch": branch,
    }
    if expected_sha:
        body["sha"] = expected_sha
    _request(url, token, "PUT", body)


def transition(filename: str, action: str, video_id: str | None = None):
    name = Path(filename).name
    if name != filename or not name.lower().endswith(".mp4"):
        raise ValueError("Filename must be a plain MP4 basename.")
    key = name.casefold()
    for attempt in range(3):
        state, sha = read()
        old = state["items"].get(key, {})
        now = datetime.now(timezone.utc).isoformat()
        if action == "reserve":
            if old.get("status") in {"reserved", "uploaded", "uncertain"}:
                raise StateConflict(f"Duplicate blocked: current status is {old['status']}.")
            new = {"filename": name, "status": "reserved", "reserved_at": now, "attempts": old.get("attempts", 0) + 1}
        elif action == "complete":
            if old.get("status") != "reserved" or not video_id:
                raise StateConflict("Completion requires a reservation and confirmed YouTube video ID.")
            new = {**old, "status": "uploaded", "video_id": video_id, "completed_at": now}
        elif action == "uncertain":
            if old.get("status") != "reserved":
                raise StateConflict("Only a reserved item can be marked uncertain.")
            new = {**old, "status": "uncertain", "updated_at": now}
        else:
            raise ValueError("Unsupported state action.")
        state["items"][key] = new
        try:
            write(state, sha)
            return new
        except StateConflict:
            if attempt == 2:
                raise
            time.sleep(1)
    raise StateConflict("Cloud queue state could not be written safely.")
