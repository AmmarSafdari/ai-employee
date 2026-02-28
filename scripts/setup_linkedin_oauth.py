"""
LinkedIn OAuth2 Setup — Run Once
==================================
Walks you through the LinkedIn OAuth 2.0 Authorization Code flow,
captures the access token, fetches your Person URN, and writes
both values to .env automatically.

Prerequisites:
  - Created a LinkedIn app at https://www.linkedin.com/developers/apps
  - Added "Share on LinkedIn" product (gives w_member_social scope)
  - Added "Sign In with OpenID Connect" product (gives openid + profile + email)

Steps:
  1. Run this script:
         python scripts/setup_linkedin_oauth.py
  2. Enter your LinkedIn app's Client ID and Client Secret when prompted
     (find them at: LinkedIn App > Auth tab > Application credentials)
  3. A browser window opens — sign in to LinkedIn and click Allow
  4. Token + Person URN are fetched and written to .env automatically

Usage:
    python scripts/setup_linkedin_oauth.py
    python scripts/setup_linkedin_oauth.py --port 8000
"""

import argparse
import io
import os
import re
import secrets
import sys
import threading
import webbrowser

# Force UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

VAULT_ROOT = Path(__file__).parent.parent

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: Run: pip install requests python-dotenv")
    sys.exit(1)

LINKEDIN_AUTH_URL  = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO  = "https://api.linkedin.com/v2/userinfo"

SCOPES = "openid profile email w_member_social"


# ── OAuth callback server ──────────────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    code   = None
    error  = None
    state  = None
    done   = threading.Event()

    def log_message(self, fmt, *args):
        pass  # suppress access logs

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _CallbackHandler.code  = params["code"][0]
            _CallbackHandler.state = params.get("state", [None])[0]
            body = b"<html><body style='font-family:sans-serif;text-align:center;padding:60px'><h2 style='color:#0a66c2'>LinkedIn connected!</h2><p>You can close this tab and return to the terminal.</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        elif "error" in params:
            _CallbackHandler.error = params.get("error_description", params.get("error", ["unknown"]))[0]
            body = b"<html><body style='font-family:sans-serif;text-align:center;padding:60px'><h2 style='color:red'>Authorization failed</h2><p>Check the terminal for details.</p></body></html>"
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

        _CallbackHandler.done.set()


def _run_callback_server(port: int) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ── .env updater ──────────────────────────────────────────────────────────────

def _update_env(token: str, author_urn: str, env_path: Path):
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    def _set(key: str, value: str, content: str) -> str:
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, re.MULTILINE):
            return re.sub(pattern, replacement, content, flags=re.MULTILINE)
        return content + f"\n{replacement}\n"

    text = _set("LINKEDIN_ACCESS_TOKEN", token, text)
    text = _set("LINKEDIN_AUTHOR_URN", author_urn, text)
    env_path.write_text(text, encoding="utf-8")


# ── main flow ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LinkedIn OAuth2 setup")
    parser.add_argument("--port", type=int, default=8000,
                        help="Local callback port (default: 8000)")
    parser.add_argument("--client-id",     default=None)
    parser.add_argument("--client-secret", default=None)
    args = parser.parse_args()

    load_dotenv(VAULT_ROOT / ".env")
    env_path = VAULT_ROOT / ".env"

    print("\n" + "="*60)
    print("  LinkedIn OAuth2 Setup")
    print("="*60)
    print()
    print("Where to find your credentials:")
    print("  linkedin.com/developers/apps > Your App > Auth tab")
    print("  Under: Application credentials\n")

    client_id = args.client_id or input("  Client ID     : ").strip()
    client_secret = args.client_secret or input("  Client Secret : ").strip()

    if not client_id or not client_secret:
        print("\nERROR: Client ID and Client Secret are required.")
        sys.exit(1)

    redirect_uri = f"http://localhost:{args.port}/callback"
    state = secrets.token_urlsafe(16)

    # ── Step 1: Build auth URL ────────────────────────────────────────────────
    auth_params = {
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "scope":         SCOPES,
        "state":         state,
    }
    auth_url = f"{LINKEDIN_AUTH_URL}?{urlencode(auth_params)}"

    # ── Step 2: Start callback server ─────────────────────────────────────────
    print(f"\n  Redirect URI (add this to your LinkedIn app if not already):")
    print(f"  {redirect_uri}\n")

    _CallbackHandler.done.clear()
    _CallbackHandler.code  = None
    _CallbackHandler.error = None

    server = _run_callback_server(args.port)
    print(f"  [1/4] Callback server ready on port {args.port}")

    # ── Step 3: Open browser ──────────────────────────────────────────────────
    print(f"  [2/4] Opening browser — sign in and click Allow...")
    print(f"\n  If the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # ── Step 4: Wait for callback ─────────────────────────────────────────────
    print("  Waiting for LinkedIn to redirect back... (timeout: 5 min)")
    _CallbackHandler.done.wait(timeout=300)
    server.shutdown()

    if _CallbackHandler.error:
        print(f"\n  ERROR from LinkedIn: {_CallbackHandler.error}")
        sys.exit(1)

    if not _CallbackHandler.code:
        print("\n  TIMEOUT — no callback received within 5 minutes.")
        sys.exit(1)

    if _CallbackHandler.state != state:
        print("\n  ERROR: State mismatch — possible CSRF. Try again.")
        sys.exit(1)

    code = _CallbackHandler.code
    print(f"  [3/4] Authorization code received.")

    # ── Step 5: Exchange code for token ───────────────────────────────────────
    print(f"  [4/4] Exchanging code for access token...")
    try:
        resp = requests.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  redirect_uri,
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except requests.HTTPError as exc:
        print(f"\n  ERROR exchanging code: {exc}")
        try:
            print(f"  Response: {exc.response.text[:400]}")
        except Exception:
            pass
        sys.exit(1)

    access_token = token_data.get("access_token")
    expires_in   = token_data.get("expires_in", 0)

    if not access_token:
        print(f"\n  ERROR: No access_token in response: {token_data}")
        sys.exit(1)

    print(f"\n  Access token received (expires in {expires_in // 3600:.0f} hours)")

    # ── Step 6: Get Person URN ─────────────────────────────────────────────────
    print("  Fetching your LinkedIn Person ID...")
    try:
        info_resp = requests.get(
            LINKEDIN_USERINFO,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        info_resp.raise_for_status()
        userinfo = info_resp.json()
    except requests.HTTPError as exc:
        print(f"\n  ERROR fetching userinfo: {exc}")
        print(f"  Response: {exc.response.text[:300]}")
        sys.exit(1)

    sub  = userinfo.get("sub")       # LinkedIn person ID
    name = userinfo.get("name", "?")

    if not sub:
        print(f"\n  ERROR: Could not get 'sub' from userinfo: {userinfo}")
        sys.exit(1)

    author_urn = f"urn:li:person:{sub}"

    # ── Step 7: Save to .env ──────────────────────────────────────────────────
    print(f"\n  Authenticated as: {name}")
    print(f"  Person ID (sub):  {sub}")
    print(f"  Author URN:       {author_urn}")

    _update_env(access_token, author_urn, env_path)

    print(f"\n" + "="*60)
    print("  SUCCESS — .env updated:")
    print(f"  LINKEDIN_ACCESS_TOKEN = {access_token[:12]}...{access_token[-4:]}")
    print(f"  LINKEDIN_AUTHOR_URN   = {author_urn}")
    print("="*60)
    print()
    print("  Next: test with")
    print("    python mcp_servers/communications.py --test")
    print("    python sentinels/linkedin_poster.py --watch")
    print()


if __name__ == "__main__":
    main()
