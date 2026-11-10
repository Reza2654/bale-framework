"""
Production-ready asynchronous HTTP client for the Bale Bot API.
Targeted at https://tapi.bale.ai (Telegram Bot API compatible).
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Mapping

import httpx

from framework.client.exceptions import (
    BaleAPIError,
    BaleAuthError,
    BaleBadRequestError,
    BaleConflictError,
    BaleConnectionTimeoutError,
    BaleNetworkError,
    BaleNotFoundError,
    BaleRateLimitError,
    BaleServerError,
)

logger = logging.getLogger("bale.client")


class BaleBotClient:
    """
    Asynchronous client for interacting with the Bale Bot API.

    Features:
    - Target base URL: https://tapi.bale.ai
    - Connection pooling and keep-alive configuration via HTTPX.
    - Automatic exponential backoff with jitter on network failures and 5xx errors.
    - Typed API methods matching Telegram Bot API specifications.
    - Token masking in string representations and logs.
    """

    DEFAULT_BASE_URL = "https://tapi.bale.ai"
    DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=15.0, pool=10.0)
    DEFAULT_LIMITS = httpx.Limits(
        max_connections=100,
        max_keepalive_connections=25,
        keepalive_expiry=30.0,
    )

    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        limits: httpx.Limits = DEFAULT_LIMITS,
        max_retries: int = 4,
        backoff_factor: float = 1.0,
        http2: bool = False,
        custom_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ValueError("Bale bot token must not be empty.")

        self._token = token
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor

        if custom_http_client is not None:
            self._client = custom_http_client
        else:
            try:
                self._client = httpx.AsyncClient(
                    timeout=timeout,
                    limits=limits,
                    http2=http2,
                )
            except ImportError:
                # Fallback if http2 was requested but h2 package is missing
                self._client = httpx.AsyncClient(
                    timeout=timeout,
                    limits=limits,
                    http2=False,
                )
        self._owns_client = custom_http_client is None
        self._is_closed = False

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def _build_url(self, method: str) -> str:
        return f"{self._base_url}/bot{self._token}/{method.lstrip('/')}"

    def _mask_token(self) -> str:
        if len(self._token) <= 8:
            return "***"
        return f"{self._token[:4]}...{self._token[-4:]}"

    def __repr__(self) -> str:
        return f"BaleBotClient(base_url={self._base_url!r}, token={self._mask_token()!r})"

    async def __aenter__(self) -> BaleBotClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTPX client connection pool."""
        if not self._is_closed:
            if self._owns_client:
                await self._client.aclose()
            self._is_closed = True
            logger.debug("BaleBotClient connection pool closed.")

    async def request(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> Any:
        """
        Execute an HTTP POST request to the Bale Bot API with automatic retries.

        :param method: Bale/Telegram API method name (e.g. 'sendMessage').
        :param payload: JSON-serializable request body parameters.
        :param files: Multipart file payloads for uploads.
        :param timeout: Optional override for per-request timeout.
        :return: Decoded 'result' field from the response JSON.
        :raises BaleAPIError: On Telegram/Bale ok=false responses.
        :raises BaleNetworkError: If transport fails after max_retries.
        """
        if self._is_closed:
            raise RuntimeError("Cannot execute request: BaleBotClient is closed.")

        url = self._build_url(method)
        clean_payload = {k: v for k, v in (payload or {}).items() if v is not None}

        attempt = 0
        while True:
            attempt += 1
            try:
                if files:
                    # Multipart upload
                    response = await self._client.post(
                        url,
                        data=clean_payload,
                        files=files,
                        timeout=timeout or httpx.USE_CLIENT_DEFAULT,
                    )
                else:
                    # Pure JSON RPC
                    response = await self._client.post(
                        url,
                        json=clean_payload,
                        timeout=timeout or httpx.USE_CLIENT_DEFAULT,
                    )

                return self._parse_response(response)

            except (httpx.TimeoutException, httpx.NetworkError, BaleServerError, BaleRateLimitError) as exc:
                if attempt > self._max_retries:
                    logger.error(
                        "Request %s failed after %d attempts: %s",
                        method,
                        self._max_retries,
                        exc,
                    )
                    if isinstance(exc, (BaleServerError, BaleRateLimitError)):
                        raise
                    if isinstance(exc, httpx.TimeoutException):
                        raise BaleConnectionTimeoutError(
                            f"Request {method} timed out: {exc}", original_error=exc
                        ) from exc
                    raise BaleNetworkError(
                        f"Network transport error during {method}: {exc}", original_error=exc
                    ) from exc

                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None and retry_after > 0:
                    delay = float(retry_after)
                else:
                    # Exponential backoff with full jitter
                    delay = (self._backoff_factor * (2 ** (attempt - 1))) + random.uniform(0.1, 0.5)

                logger.warning(
                    "Attempt %d/%d for method %s encountered error (%s). Retrying in %.2fs...",
                    attempt,
                    self._max_retries,
                    method,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    def _parse_response(self, response: httpx.Response) -> Any:
        """Parse and validate JSON response from Bale."""
        try:
            data = response.json()
        except Exception as json_err:
            if response.status_code >= 500:
                raise BaleServerError(
                    error_code=response.status_code,
                    description=f"Server returned non-JSON error: {response.text[:200]}",
                ) from json_err
            raise BaleAPIError(
                error_code=response.status_code,
                description=f"Malformed JSON from API: {response.text[:200]}",
            ) from json_err

        if not isinstance(data, dict):
            raise BaleAPIError(
                error_code=response.status_code,
                description=f"Unexpected response format: {type(data).__name__}",
            )

        if data.get("ok") is True:
            return data.get("result")

        # Handle API error (ok=false)
        error_code = data.get("error_code", response.status_code)
        description = data.get("description", "Unknown error from Bale API")
        parameters = data.get("parameters") or {}

        logger.debug("API call returned error: [%d] %s (params: %s)", error_code, description, parameters)

        if error_code in (401, 403):
            raise BaleAuthError(error_code, description, parameters, data)
        if error_code == 400:
            raise BaleBadRequestError(error_code, description, parameters, data)
        if error_code == 404:
            raise BaleNotFoundError(error_code, description, parameters, data)
        if error_code == 409:
            raise BaleConflictError(error_code, description, parameters, data)
        if error_code == 429:
            raise BaleRateLimitError(error_code, description, parameters, data)
        if error_code >= 500:
            raise BaleServerError(error_code, description, parameters, data)

        raise BaleAPIError(error_code, description, parameters, data)

    # ==========================================
    # High-level typed API methods
    # ==========================================

    async def get_me(self) -> dict[str, Any]:
        """Verify bot token and fetch bot identity details."""
        result = await self.request("getMe")
        return result  # type: ignore[no-any-return]

    async def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 20,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Poll for incoming updates from Bale via long-polling.

        :param offset: Identifier of the first update to be returned.
        :param limit: Limits the number of updates to be retrieved (1-100).
        :param timeout: Long-polling timeout in seconds.
        :param allowed_updates: List of update types to receive (e.g. ['message', 'callback_query']).
        :return: List of update dictionaries.
        """
        payload: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "timeout": timeout,
            "allowed_updates": allowed_updates,
        }
        # Dynamic read timeout: poll timeout + 15s padding for network transit
        request_timeout = httpx.Timeout(
            connect=10.0,
            read=float(timeout + 15),
            write=10.0,
            pool=10.0,
        )
        result = await self.request("getUpdates", payload=payload, timeout=request_timeout)
        return result or []

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
        disable_web_page_preview: bool | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, Any]:
        """
        Send a text message to a specific chat/user.

        :param chat_id: Target user or group chat ID.
        :param text: Text of the message to be sent.
        :param parse_mode: Formatting mode ('HTML', 'MarkdownV2', or None).
        :param reply_markup: InlineKeyboardMarkup or ReplyKeyboardMarkup dict.
        :param reply_to_message_id: If replying to a specific message ID.
        :param disable_web_page_preview: Disables link previews for links in this message.
        :param disable_notification: Sends the message silently.
        :return: Sent Message dictionary.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            "reply_to_message_id": reply_to_message_id,
            "disable_web_page_preview": disable_web_page_preview,
            "disable_notification": disable_notification,
        }
        result = await self.request("sendMessage", payload=payload)
        return result  # type: ignore[no-any-return]

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
        url: str | None = None,
        cache_time: int | None = None,
    ) -> bool:
        """
        Send answer to callback query sent from inline keyboard buttons.

        :param callback_query_id: Unique identifier for the query to be answered.
        :param text: Text notification shown to the user.
        :param show_alert: If True, an alert modal is shown instead of a toast notification.
        :param url: URL that will be opened by the user's client.
        :param cache_time: The maximum amount of time in seconds that the result may be cached.
        :return: True on success.
        """
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
            "url": url,
            "cache_time": cache_time,
        }
        result = await self.request("answerCallbackQuery", payload=payload)
        return bool(result)

    async def set_webhook(
        self,
        url: str,
        secret_token: str | None = None,
        max_connections: int | None = None,
        allowed_updates: list[str] | None = None,
        drop_pending_updates: bool = False,
    ) -> bool:
        """Specify a URL and receive incoming updates via outgoing webhook."""
        payload: dict[str, Any] = {
            "url": url,
            "secret_token": secret_token,
            "max_connections": max_connections,
            "allowed_updates": allowed_updates,
            "drop_pending_updates": drop_pending_updates,
        }
        result = await self.request("setWebhook", payload=payload)
        return bool(result)

    async def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        """Remove webhook integration if switching to long-polling."""
        payload = {"drop_pending_updates": drop_pending_updates}
        result = await self.request("deleteWebhook", payload=payload)
        return bool(result)

    async def get_webhook_info(self) -> dict[str, Any]:
        """Get current webhook status."""
        result = await self.request("getWebhookInfo")
        return result  # type: ignore[no-any-return]
