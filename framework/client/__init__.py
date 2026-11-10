"""Client package exports."""

from framework.client.client import BaleBotClient
from framework.client.exceptions import (
    BaleAPIError,
    BaleAuthError,
    BaleBadRequestError,
    BaleConflictError,
    BaleConnectionTimeoutError,
    BaleError,
    BaleNetworkError,
    BaleNotFoundError,
    BaleRateLimitError,
    BaleServerError,
)

__all__ = [
    "BaleBotClient",
    "BaleError",
    "BaleNetworkError",
    "BaleConnectionTimeoutError",
    "BaleAPIError",
    "BaleAuthError",
    "BaleBadRequestError",
    "BaleNotFoundError",
    "BaleConflictError",
    "BaleRateLimitError",
    "BaleServerError",
]
