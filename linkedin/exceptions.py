class LinkedInAPIError(Exception):
    def __init__(self, status_code: int, message: str, error_code: int = 0):
        self.status_code = status_code
        self.message = message
        self.error_code = error_code
        super().__init__(f"LinkedIn API error {status_code}: {message}")


class TokenExpiredError(LinkedInAPIError):
    def __init__(self, message: str = "Token expired. Run 'python main.py login' to re-authenticate."):
        super().__init__(status_code=401, message=message, error_code=0)
