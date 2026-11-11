"""Local persistent duplicate-prevention ledger; no network or publishing code."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FINAL = {"uploaded", "scheduled"}


def key(filename):
    return hashlib.sha256(Path(filename).name.casefold().encode()).hexdigest()


def read_state(path):
    p = Path(path)
    if not p.exists(): return {"schema_version": 1, "items": {}}
    state = json.loads(p.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1 or not isinstance(state.get("items"), dict):
        raise ValueError("Unsupported state file")
    return state


def write_state(path, state):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def transition(path, filename, action, youtube_video_id=None):
    if action not in {"reserve", "complete", "fail", "reconcile"}: raise ValueError("Unsupported state action")
    state = read_state(path); k = key(filename); old = state["items"].get(k, {})
    now = datetime.now(timezone.utc).isoformat()
    if action == "reserve":
        if old.get("status") in FINAL | {"in_flight"}: raise ValueError(f"Duplicate blocked: status={old.get('status')}")
        new = {"filename": Path(filename).name, "status": "in_flight", "reserved_at": now, "attempts": old.get("attempts", 0)+1}
    elif action == "complete":
        if old.get("status") != "in_flight": raise ValueError("Completion requires an in_flight reservation")
        new = {**old, "status": "uploaded", "completed_at": now, "youtube_video_id": youtube_video_id}
    elif action == "fail":
        if old.get("status") not in {"in_flight", "reconcile_required"}: raise ValueError("Failure requires an active or uncertain attempt")
        new = {**old, "status": "failed", "failed_at": now}
    else:
        if old.get("status") not in {"in_flight", "failed", "reconcile_required"}: raise ValueError("Only uncertain/failed items can require reconciliation")
        new = {**old, "status": "reconcile_required", "reconciled_at": now}
    state["items"][k] = new; write_state(path, state)
    return new["status"]
