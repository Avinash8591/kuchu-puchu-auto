#!/usr/bin/env python3
"""One-time Dropbox OAuth PKCE setup for Kuchu Puchu Auto Publisher.

Run locally on the user's Windows PC. This script never sends credentials to
this repository; it prints the refresh token once so it can be saved directly
as a GitHub Actions secret.
"""
import base64
import hashlib
import http.server
import secrets
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
import json

APP_KEY = "6yurgibs12cz4cy"
REDIRECT_URI = "http://localhost:53682/callback"
AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode("ascii")).digest()
).rstrip(b"=").decode("ascii")
state = secrets.token_urlsafe(24)

callback_result = {}

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path != "/callback":
            self.send_error(404)
            return
        if params.get("state", [""])[0] != state:
            callback_result["error"] = "OAuth state mismatch. Do not use this result."
        elif "error" in params:
            callback_result["error"] = params.get("error_description", params["error"])[0]
        else:
            callback_result["code"] = params.get("code", [""])[0]
        body = (b"Dropbox authorization received. You can close this browser tab "
                b"and return to the terminal.")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

query = urllib.parse.urlencode({
    "client_id": APP_KEY,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "token_access_type": "offline",
    "code_challenge": challenge,
    "code_challenge_method": "S256",
    "state": state,
})
url = f"{AUTHORIZE_URL}?{query}"

server = http.server.HTTPServer(("localhost", 53682), CallbackHandler)
server.timeout = 300

print("Opening Dropbox authorization in your browser...")
print("If it does not open, visit this URL:")
print(url)
webbrowser.open(url)

while not callback_result:
    server.handle_request()
server.server_close()

if "error" in callback_result:
    raise SystemExit("Authorization failed: " + callback_result["error"])

form = urllib.parse.urlencode({
    "code": callback_result["code"],
    "grant_type": "authorization_code",
    "client_id": APP_KEY,
    "redirect_uri": REDIRECT_URI,
    "code_verifier": verifier,
}).encode("utf-8")
request = urllib.request.Request(
    TOKEN_URL,
    data=form,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        token_data = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"Dropbox token exchange failed ({exc.code}): {detail}")

refresh_token = token_data.get("refresh_token")
if not refresh_token:
    raise SystemExit("Dropbox did not return a refresh token. Check app settings and retry.")

print("\nSUCCESS. Copy the refresh token below directly into GitHub Actions Secrets.")
print("Do not send it in chat, commit it to GitHub, or share a screenshot containing it.")
print("\nDROPBOX_REFRESH_TOKEN:")
print(refresh_token)
