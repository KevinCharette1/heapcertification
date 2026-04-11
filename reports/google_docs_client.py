import json
import warnings
import urllib3
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests as _requests

from .exceptions import GoogleDocsAPIError

# Suppress SSL warnings from the egress proxy's self-signed cert
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCOPES = ["https://www.googleapis.com/auth/documents"]
TOKEN_FILE = Path("google_tokens.json")
SEPARATOR = "\n" + "\u2500" * 60 + "\n\n"


def _get_credentials(client_secrets_file: str) -> Credentials:
    """
    Load saved OAuth credentials or prompt the user to authorize.
    Tokens are saved to google_tokens.json for reuse.
    """
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh using a session with SSL verification disabled
            session = _requests.Session()
            session.verify = False
            try:
                creds.refresh(GoogleRequest(session=session))
            except Exception as e:
                creds = None  # Force re-auth if refresh fails

        if not creds or not creds.valid:
            if not Path(client_secrets_file).exists():
                raise GoogleDocsAPIError(
                    f"Google OAuth client secrets file not found: {client_secrets_file}\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials\n"
                    "→ Create OAuth 2.0 Client ID (Desktop app) → Download JSON"
                )
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save for future runs
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)

    return creds


import httplib2

# Monkey-patch httplib2 to disable SSL cert verification (egress proxy self-signed cert)
_OrigHttp = httplib2.Http
class _NoSSLHttp(_OrigHttp):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("disable_ssl_certificate_validation", True)
        super().__init__(*args, **kwargs)
httplib2.Http = _NoSSLHttp


class GoogleDocsClient:
    def __init__(self, client_secrets_file: str = "google_client_secret.json"):
        try:
            creds = _get_credentials(client_secrets_file)
            self._service = build("docs", "v1", credentials=creds, cache_discovery=False)
            self._creds = creds
        except GoogleDocsAPIError:
            raise
        except Exception as e:
            raise GoogleDocsAPIError(f"Failed to initialize Google Docs client: {e}")

    def read_doc_text(self, doc_id: str) -> str:
        """Fetch the full plain-text content of a Google Doc."""
        try:
            doc = self._service.documents().get(documentId=doc_id).execute()
        except Exception as e:
            raise GoogleDocsAPIError(f"Failed to read doc '{doc_id}': {e}")
        return _extract_text(doc)

    def prepend_to_doc(self, doc_id: str, text: str) -> None:
        """
        Insert text at the very beginning of a Google Doc (index 1),
        followed by a visual separator line.
        """
        full_insert = text + SEPARATOR
        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": full_insert,
                }
            }
        ]
        try:
            self._service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()
        except Exception as e:
            raise GoogleDocsAPIError(f"Failed to prepend to doc '{doc_id}': {e}")


def _extract_text(doc: dict) -> str:
    """Walk the document body and collect all paragraph text."""
    parts = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for pe in paragraph.get("elements", []):
            text_run = pe.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)
