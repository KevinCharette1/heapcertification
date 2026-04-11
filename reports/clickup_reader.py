import json
from pathlib import Path

from .exceptions import ClickUpAPIError

# Cache file written by Claude Code before running the script.
# The ClickUp API is not directly reachable from this environment —
# content is pre-fetched via MCP tools and stored here.
CACHE_FILE = Path("clickup_cache.json")


class ClickUpReader:
    def __init__(self, api_token: str, workspace_id: str):
        self._token = api_token
        self._workspace_id = workspace_id
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if CACHE_FILE.exists():
            with open(CACHE_FILE) as f:
                return json.load(f)
        return {}

    def fetch_doc_content(self, doc_id: str, page_id: str | None = None) -> str:
        """
        Fetch the text content of a ClickUp Doc page as Markdown.
        Reads from clickup_cache.json (pre-fetched via MCP before running the script).
        """
        doc_cache = self._cache.get(doc_id)
        if not doc_cache:
            raise ClickUpAPIError(
                status_code=0,
                message=(
                    f"No cached content found for ClickUp doc '{doc_id}'. "
                    "Run the ClickUp pre-fetch step before running reports."
                ),
            )

        if page_id:
            content = doc_cache.get(page_id)
            if content is None:
                raise ClickUpAPIError(
                    status_code=0,
                    message=f"No cached content for page '{page_id}' in doc '{doc_id}'.",
                )
            return content

        # No page_id — return the latest page (highest numeric ID)
        def page_num(pid: str) -> int:
            try:
                return int(pid.rsplit("-", 1)[-1])
            except (ValueError, IndexError):
                return 0

        latest_page_id = max(doc_cache.keys(), key=page_num)
        return doc_cache[latest_page_id]

    def close(self) -> None:
        pass
