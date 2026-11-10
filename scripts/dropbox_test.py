import json
import os
import sys
import urllib.request
import urllib.error

ACCESS_TOKEN = os.environ["DROPBOX_ACCESS_TOKEN"]
FOLDER_PATH = "/kuchu puchu tap karo_"

def dropbox_post(endpoint, payload):
    request = urllib.request.Request(
        f"https://api.dropboxapi.com/2/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Dropbox API returned HTTP {exc.code}: {body[:500]}", file=sys.stderr)
        raise

def numeric_key(name):
    stem = name.rsplit(".", 1)[0]
    try:
        return (0, int(stem), name.lower())
    except ValueError:
        return (1, stem.lower(), name.lower())

def main():
    result = dropbox_post("files/list_folder", {
        "path": FOLDER_PATH,
        "recursive": False,
        "include_deleted": False,
        "include_non_downloadable_files": False,
    })

    entries = result.get("entries", [])
    while result.get("has_more"):
        result = dropbox_post("files/list_folder/continue", {
            "cursor": result["cursor"]
        })
        entries.extend(result.get("entries", []))

    videos = sorted(
        [item["name"] for item in entries
         if item.get(".tag") == "file"
         and item["name"].lower().endswith(".mp4")],
        key=numeric_key,
    )
    queue = [name for name in videos if name != "001.mp4"]

    print(f"Dropbox connection: OK")
    print(f"Folder: {FOLDER_PATH}")
    print(f"MP4 files found: {len(videos)}")
    print(f"Excluded as already scheduled: 001.mp4")
    print(f"Remaining queue size: {len(queue)}")
    print("First 10 queued filenames:")
    for name in queue[:10]:
        print(f" - {name}")

    if not videos:
        raise SystemExit("No MP4 files found. Check the configured Dropbox folder path.")

if __name__ == "__main__":
    main()
