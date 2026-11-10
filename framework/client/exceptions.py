"""Exception hierarchy for the Bale Bot API client."""

from __future__ import annotations

from typing import Any


class BaleError(Exception):
    """Base exception class for all errors originating within the Bale framework."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r})"


class BaleNetworkError(BaleError):
    """Raised when an underlying transport/network error occurs."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class BaleConnectionTimeoutError(BaleNetworkError):
    """Raised when a connection or read attempt times out."""


class BaleAPIError(BaleError):
    """
    Raised when the Bale API returns an error response (ok=false).

    Compatible with standard Telegram Bot API response structure:
    {"ok": false, "error_code": 400, "description": "Bad Request: ...", "parameters": {...}}
    """

    def __init__(
        self,
        error_code: int,
        description: str,
        parameters: dict[str, Any] | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{error_code}] {description}")
        self.error_code = error_code
        self.description = description
        self.parameters = parameters or {}
        self.raw_response = raw_response or {}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code}, "
            f"description={self.description!r}, "
            f"parameters={self.parameters!r})"
        )


class BaleAuthError(BaleAPIError):
    """Raised when authentication fails (HTTP 401/403 or invalid bot token)."""


class BaleBadRequestError(BaleAPIError):
    """Raised when an invalid request payload is sent (HTTP 400)."""


class BaleNotFoundError(BaleAPIError):
    """Raised when the requested endpoint or resource cannot be found (HTTP 404)."""


class BaleConflictError(BaleAPIError):
    """
    Raised when an operational conflict occurs (HTTP 409).

    E.g. Webhook is already set while starting long-polling, or another
    instance is actively consuming updates with the same token.
    """


class BaleRateLimitError(BaleAPIError):
    """Raised when the bot exceeds Bale's API rate limits (HTTP 429)."""

    def __init__(
        self,
        error_code: int,
        description: str,
        parameters: dict[str, Any] | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, description, parameters, raw_response)
        # Extract retry_after parameter if provided by the API
        self.retry_after: int | None = self.parameters.get("retry_after")


class BaleServerError(BaleAPIError):
    """Raised when Bale returns 5xx internal server/gateway errors."""
