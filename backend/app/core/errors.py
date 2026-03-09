from typing import Any, Dict, Optional


class AppError(Exception):
    """Base exception for application-specific errors that should be returned to the client."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
