import httpx

from .exceptions import ClickUpAPIError

BASE_URL = "https://api.clickup.com/api/v3"


class ClickUpReader:
    def __init__(self, api_token: str, workspace_id: str):
        self._token = api_token
        self._workspace_id = workspace_id
        self._http = httpx.Client(timeout=30.0)

    def _headers(self) -> dict:
        return {
            "Authorization": self._token,  # ClickUp uses bare token, no "Bearer" prefix
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        response = self._http.request(method, url, headers=self._headers(), **kwargs)
        if not response.is_success:
            raise ClickUpAPIError(
                status_code=response.status_code,
                message=response.text,
            )
        return response.json()

    def fetch_doc_content(self, doc_id: str, page_id: str | None = None) -> str:
        """
        Fetch the text content of a ClickUp Doc page as Markdown.
        If page_id is None, auto-fetches the first page of the doc.
        """
        if page_id is None:
            page_id = self._get_latest_page_id(doc_id)

        data = self._request(
            "GET",
            f"workspaces/{self._workspace_id}/docs/{doc_id}/pages/{page_id}",
            params={"content_format": "text/md"},
        )
        return data.get("content", "")

    def _get_latest_page_id(self, doc_id: str) -> str:
        """Return the ID of the most recently created page (highest numeric ID)."""
        data = self._request(
            "GET",
            f"workspaces/{self._workspace_id}/docs/{doc_id}/pages",
        )
        pages = data.get("pages", [])
        if not pages:
            raise ClickUpAPIError(
                status_code=0,
                message=f"ClickUp Doc '{doc_id}' has no pages.",
            )
        # Page IDs are formatted as "<prefix>-<number>"; sort by the numeric suffix
        def page_num(p: dict) -> int:
            try:
                return int(p["id"].rsplit("-", 1)[-1])
            except (ValueError, IndexError):
                return 0
        return max(pages, key=page_num)["id"]

    def close(self) -> None:
        self._http.close()
