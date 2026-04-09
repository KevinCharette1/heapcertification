"""
LinkedIn OAuth 2.0 Authorization Code flow for CLI use.

Works in two modes:
  - Auto: local HTTP server catches the redirect (only works when browser
    and Python are on the same machine)
  - Manual fallback: user pastes the redirect URL from their browser's
    address bar after seeing "localhost refused to connect"
"""

import queue
import secrets
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
SCOPES = "r_ads rw_ads w_organization_social"
CALLBACK_PORT = 8888


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot HTTP handler that captures the OAuth callback."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            self.server.result_queue.put(params)

            body = b"""
            <html>
              <body style="font-family:sans-serif;text-align:center;padding-top:80px">
                <h2>Authorization complete!</h2>
                <p>You can close this tab and return to the terminal.</p>
              </body>
            </html>
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def run_oauth_flow(settings) -> dict:
    """
    Run the full OAuth flow interactively.
    Returns a token dict ready to be saved to tokens.json.
    """
    state = secrets.token_hex(16)

    auth_url = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.linkedin_client_id}"
        f"&redirect_uri={settings.linkedin_redirect_uri}"
        f"&state={state}"
        f"&scope={SCOPES.replace(' ', '%20')}"
    )

    result_queue: queue.Queue = queue.Queue()

    # Try starting local server (works when browser + Python are on same machine)
    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server.result_queue = result_queue
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("\nOpen this URL in your browser to authorize:\n")
    print(f"  {auth_url}\n")
    webbrowser.open(auth_url)

    print("─" * 60)
    print("After clicking Allow, one of two things will happen:\n")
    print("  A) Page shows 'Authorization complete!' → done automatically.\n")
    print("  B) Page shows 'localhost refused to connect' → copy the FULL")
    print("     URL from your browser's address bar and paste it below.")
    print("     (It starts with: http://localhost:8888/callback?code=...)\n")

    # Accept manual paste in a background thread
    def _read_manual():
        try:
            url = input("Paste callback URL here (or wait for auto-capture): ").strip()
            if url:
                params = parse_qs(urlparse(url).query)
                result_queue.put(params)
        except EOFError:
            pass

    input_thread = threading.Thread(target=_read_manual, daemon=True)
    input_thread.start()

    try:
        params = result_queue.get(timeout=300)
    except queue.Empty:
        raise RuntimeError("Authorization timed out after 5 minutes. Please try again.")

    error = params.get("error", [None])[0]
    if error:
        raise RuntimeError(f"LinkedIn authorization denied: {error}")

    received_code = params.get("code", [None])[0]
    received_state = params.get("state", [None])[0]

    if not received_code:
        raise RuntimeError("No authorization code received. Please try again.")

    if received_state != state:
        raise RuntimeError("State mismatch — possible CSRF. Please try again.")

    print("\nAuthorization code received. Exchanging for tokens...")
    return _exchange_code(code=received_code, settings=settings)


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

    # Fetch member profile to store name + URN
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
    Raises TokenExpiredError if refresh fails.
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
