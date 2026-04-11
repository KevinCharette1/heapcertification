import urllib3
import httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .exceptions import GoogleDocsAPIError

# Suppress SSL warnings from the egress proxy's self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkey-patch httplib2 to disable SSL cert verification globally —
# required because the egress proxy uses its own cert
_OrigHttplib2Http = httplib2.Http
class _NoSSLHttp(_OrigHttplib2Http):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("disable_ssl_certificate_validation", True)
        super().__init__(*args, **kwargs)
httplib2.Http = _NoSSLHttp

SCOPES = ["https://www.googleapis.com/auth/documents"]
SEPARATOR = "\n" + "\u2500" * 60 + "\n\n"


class GoogleDocsClient:
    def __init__(self, service_account_key_file: str):
        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_key_file,
                scopes=SCOPES,
            )
            self._service = build("docs", "v1", credentials=creds, cache_discovery=False)
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
        Uses a single batchUpdate insertText request — atomic, no read needed first.
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
