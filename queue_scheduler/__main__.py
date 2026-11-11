"""Offline preview planner. Deliberately has no upload or scheduling side effects."""
import argparse
import hashlib
import json
import re
from pathlib import Path

EXCLUDED = {"001.mp4", "3932954021832974372.mp4"}


def sort_key(name):
    stem = Path(name).stem
    match = re.match(r"^(\d+)", stem)
    return (0, int(match.group(1)), name.casefold()) if match else (1, 0, name.casefold())


def metadata(filename):
    stem = Path(filename).stem
    label = re.sub(r"[_-]+", " ", stem)
    label = re.sub(r"\s+", " ", label).strip()
    label = label[:65] or "Kuchu Puchu"
    return {
        "title": f"Kuchu Puchu | {label}"[:100],
        "description": "A little Kuchu Puchu moment for the family to enjoy.\n\n#KuchuPuchu #KidsVideo #Shorts",
        "category_id": "22",
        "privacy_status": "private",
    }


def preview(listing, output):
    names = [line.strip() for line in Path(listing).read_text(encoding="utf-8").splitlines() if line.strip()]
    mp4s = [Path(n).name for n in names if Path(n).suffix.casefold() == ".mp4"]
    unique = sorted(set(mp4s), key=sort_key)
    items = []
    for i, name in enumerate((n for n in unique if n.casefold() not in {x.casefold() for x in EXCLUDED}), 1):
        items.append({
            "queue_id": hashlib.sha256(name.casefold().encode()).hexdigest(),
            "filename": name,
            "sequence": i,
            "status": "pending",
            "metadata": metadata(name),
        })
    manifest = {"schema_version": 1, "mode": "preview_only", "source_folder": "/kuchu puchu tap karo_", "excluded": sorted(EXCLUDED), "items": items}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Preview only: {len(items)} eligible MP4 files. No upload or schedule was attempted. Output: {output}")


def main():
    parser = argparse.ArgumentParser(description="Build an offline, preview-only upload queue.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preview")
    p.add_argument("--files-list", required=True, help="UTF-8 text file, one Dropbox filename per line")
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "preview":
        preview(args.files_list, args.output)


if __name__ == "__main__":
    main()
