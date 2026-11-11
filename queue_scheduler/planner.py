"""Dropbox filename parsing and deterministic offline manifest preview."""
import hashlib
import json
import re
from pathlib import Path

EXCLUDED = {"001.mp4", "3932954021832974372.mp4"}


def sort_key(name):
    m = re.match(r"^(\d+)", Path(name).stem)
    return (0, int(m.group(1)), name.casefold()) if m else (1, 0, name.casefold())


def load_names(path):
    names = [Path(line.strip()).name for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    return sorted({n for n in names if Path(n).suffix.casefold() == ".mp4" and n.casefold() not in {x.casefold() for x in EXCLUDED}}, key=sort_key)


def metadata(name):
    label = re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", Path(name).stem)).strip()[:65] or "Kuchu Puchu"
    return {"title": f"Kuchu Puchu | {label}"[:100], "description": "A little Kuchu Puchu moment for the family to enjoy.\n\n#KuchuPuchu #KidsVideo #Shorts", "category_id": "22", "privacy_status": "private"}


def preview(listing, output):
    names = load_names(listing)
    items = [{"queue_id": hashlib.sha256(n.casefold().encode()).hexdigest(), "filename": n, "sequence": i, "status": "pending", "metadata": metadata(n)} for i, n in enumerate(names, 1)]
    data = {"schema_version": 1, "mode": "manual_review_only", "source_folder": "/kuchu puchu tap karo_", "excluded": sorted(EXCLUDED), "items": items}
    p = Path(output); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Preview only: {len(items)} eligible files. No external service call, upload, or schedule was attempted.")
