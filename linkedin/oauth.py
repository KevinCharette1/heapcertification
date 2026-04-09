"""
LinkedIn OAuth 2.0 Authorization Code flow for CLI use.

Two-step flow for remote/cloud environments:

  Step 1 — python main.py login
    Prints the authorization URL. User opens it in a browser.
    State token is saved to .oauth_state for later validation.

  Step 2 — python main.py login 'http://localhost:8888/callback?code=...&state=...'
    User pastes the full redirect URL from their browser address bar.
    Script validates state, exchanges code for tokens, writes tokens.json.

If browser and Python are on the same machine, the local HTTP server
catches the redirect automatically and Step 2 is not needed.
"""

import secrets
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
SCOPES = "r_ads rw_ads w_organization_social"
CALLBACK_PORT = 8888
STATE_FILE = Path(".oauth_state")


def show_oauth_url(settings) -> None:
    """
    Step 1: Print the authorization URL and save state for later validation.
    Starts a background local server in case the browser is on the same machine.
    """
    state = secrets.token_hex(16)
    STATE_FILE.write_text(state)

    auth_url = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.linkedin_client_id}"
        f"&redirect_uri={settings.linkedin_redirect_uri}"
        f"&state={state}"
        f"&scope={SCOPES.replace(' ', '%20')}"
    )

    # Try starting local server (works if browser + Python are on same machine)
    try:
        server = _make_local_server(state, settings)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        local_server_started = True
    except OSError:
        local_server_started = False

    webbrowser.open(auth_url)

    print("\nOpen this URL in your browser to authorize LinkedIn:\n")
    print(f"  {auth_url}\n")
    print("─" * 60)

    if local_server_started:
        print("Waiting for the browser redirect", end="", flush=True)
        # Poll until server catches the callback (max 5 min)
        for _ in range(300):
            import time
            time.sleep(1)
            print(".", end="", flush=True)
            if not STATE_FILE.exists():
                # Server wrote tokens.json and removed state file
                print("\n")
                return
        print("\nTimed out waiting for browser redirect.")

    print("\nIf you see 'localhost refused to connect' in your browser:")
    print("  1. Copy the FULL URL from your browser's address bar")
    print("     (starts with: http://localhost:8888/callback?code=...)")
    print("  2. Run:  python main.py login 'PASTE_FULL_URL_HERE'\n")


def complete_oauth_from_url(callback_url: str, settings) -> dict:
    """
    Step 2: Complete OAuth using the callback URL pasted from the browser.
    Validates the state token saved by show_oauth_url(), then exchanges the code.
    """
    params = parse_qs(urlparse(callback_url).query)

    error = params.get("error", [None])[0]
    if error:
        raise RuntimeError(f"LinkedIn authorization denied: {error}")

    received_code = params.get("code", [None])[0]
    received_state = params.get("state", [None])[0]

    if not received_code:
        raise ValueError(
            "No 'code' parameter found in the URL. "
            "Make sure you copied the full redirect URL."
        )

    # Validate state if we have one saved
    if STATE_FILE.exists():
        expected_state = STATE_FILE.read_text().strip()
        if received_state != expected_state:
            raise RuntimeError(
                "State mismatch — this URL doesn't match the current login session. "
                "Run 'python main.py login' again to start a fresh flow."
            )
        STATE_FILE.unlink()

    print("Exchanging authorization code for tokens...")
    return _exchange_code(code=received_code, settings=settings)


def _make_local_server(state: str, settings) -> HTTPServer:
    """Create a local HTTP server that auto-completes the OAuth flow."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            recv_state = params.get("state", [None])[0]

            if recv_state != state:
                body = b"<h2>Error: state mismatch</h2>"
                status = 400
            elif not code:
                body = b"<h2>Error: no code received</h2>"
                status = 400
            else:
                try:
                    tokens = _exchange_code(code, settings)
                    _save_tokens_and_clear_state(tokens)
                    body = b"""
                    <html><body style="font-family:sans-serif;text-align:center;padding-top:80px">
                    <h2>Authorization complete!</h2>
                    <p>You can close this tab and return to the terminal.</p>
                    </body></html>"""
                    status = 200
                except Exception as e:
                    body = f"<h2>Error: {e}</h2>".encode()
                    status = 500

            self.send_response(status)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *args):
            pass

    return HTTPServer(("localhost", CALLBACK_PORT), _Handler)


def _save_tokens_and_clear_state(tokens: dict) -> None:
    import json
    from pathlib import Path as P
    with open(P("tokens.json"), "w") as f:
        json.dump(tokens, f, indent=2)
    P("tokens.json").chmod(0o600)
    STATE_FILE.unlink(missing_ok=True)


def _exchange_code(code: str, settings) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.linkedin_redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expiry": expiry.isoformat(),
        "member_id": None,
    }

    try:
        me = httpx.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
            timeout=10,
        )
        if me.is_success:
            profile = me.json()
            tokens["member_id"] = f"urn:li:person:{profile.get('id', '')}"
            name = f"{profile.get('localizedFirstName', '')} {profile.get('localizedLastName', '')}".strip()
            tokens["member_name"] = name
    except Exception:
        pass

    return tokens


def refresh_tokens(tokens: dict, settings) -> dict:
    """Use a refresh token to get a new access token."""
    from linkedin.exceptions import TokenExpiredError

    if not tokens.get("refresh_token"):
        raise TokenExpiredError()

    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if not response.is_success:
        raise TokenExpiredError()

    data = response.json()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
    tokens["access_token"] = data["access_token"]
    tokens["expiry"] = expiry.isoformat()
    if "refresh_token" in data:
        tokens["refresh_token"] = data["refresh_token"]

    return tokens




def _exchange_code(code: str, settings) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.linkedin_redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])

    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expiry": expiry.isoformat(),
        "member_id": None,  # fetched separately in main.py
    }

    # Optionally fetch the member profile to store member URN
    try:
        me = httpx.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
            timeout=10,
        )
        if me.is_success:
            profile = me.json()
            tokens["member_id"] = f"urn:li:person:{profile.get('id', '')}"
            name = f"{profile.get('localizedFirstName', '')} {profile.get('localizedLastName', '')}".strip()
            tokens["member_name"] = name
    except Exception:
        pass

    return tokens


def refresh_tokens(tokens: dict, settings) -> dict:
    """
    Use a refresh token to get a new access token.
    Returns an updated token dict; raises TokenExpiredError if refresh fails.
    """
    from linkedin.exceptions import TokenExpiredError

    if not tokens.get("refresh_token"):
        raise TokenExpiredError()

    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if not response.is_success:
        raise TokenExpiredError()

    data = response.json()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])

    tokens["access_token"] = data["access_token"]
    tokens["expiry"] = expiry.isoformat()
    if "refresh_token" in data:
        tokens["refresh_token"] = data["refresh_token"]

    return tokens
