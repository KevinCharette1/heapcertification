class ClickUpAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"ClickUp API error {status_code}: {message}")


class GoogleDocsAPIError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Google Docs API error: {message}")
