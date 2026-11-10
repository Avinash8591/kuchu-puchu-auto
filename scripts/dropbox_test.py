import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

APP_KEY = os.environ["DROPBOX_APP_KEY"]
REFRESH_TOKEN = os.environ["DROPBOX_REFRESH_TOKEN"]
FOLDER_PATH = "/kuchu puchu tap karo_"

def get_access_token():
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": APP_KEY,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.dropboxapi.com/oauth2/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Dropbox OAuth refresh failed (HTTP {exc.code}): {body[:500]}", file=sys.stderr)
        raise
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("Dropbox OAuth response did not include an access token.")
    return access_token

def dropbox_post(access_token, endpoint, payload):
    request = urllib.request.Request(
        f"https://api.dropboxapi.com/2/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
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
    access_token = get_access_token()
    print("Dropbox OAuth refresh: OK")

    result = dropbox_post(access_token, "files/list_folder", {
        "path": FOLDER_PATH,
        "recursive": False,
        "include_deleted": False,
        "include_non_downloadable_files": False,
    })

    entries = result.get("entries", [])
    while result.get("has_more"):
        result = dropbox_post(access_token, "files/list_folder/continue", {
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

    print("Dropbox connection: OK")
    print(f"Folder: {FOLDER_PATH}")
    print(f"MP4 files found: {len(videos)}")
    print("Excluded as already scheduled: 001.mp4")
    print(f"Remaining queue size: {len(queue)}")
    print("First 10 queued filenames:")
    for name in queue[:10]:
        print(f" - {name}")

    if not videos:
        raise SystemExit("No MP4 files found. Check the configured Dropbox folder path.")

if __name__ == "__main__":
    main()
