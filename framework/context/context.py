"""
Execution context encapsulating an incoming update, bot client, and dependency data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.client.client import BaleBotClient


class BaleContext:
    """
    Strongly typed execution context for incoming Bale updates.

    Carries:
    - Raw update and extracted models (Message, CallbackQuery, Chat, User)
    - Client instance for API operations
    - Dependency injection dictionary `data` populated by middlewares
    - Shortcut convenience helpers (reply, send, answer)
    """

    def __init__(
        self,
        update: dict[str, Any],
        client: BaleBotClient,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.raw_update = update
        self.client = client
        self.data: dict[str, Any] = data if data is not None else {}

    @property
    def update_id(self) -> int:
        """Unique identifier of the update."""
        return self.raw_update.get("update_id", 0)

    @property
    def message(self) -> dict[str, Any] | None:
        """Extracts the message object if present in the update."""
        return self.raw_update.get("message")

    @property
    def edited_message(self) -> dict[str, Any] | None:
        """Extracts the edited_message object if present."""
        return self.raw_update.get("edited_message")

    @property
    def callback_query(self) -> dict[str, Any] | None:
        """Extracts the callback_query object if present in the update."""
        return self.raw_update.get("callback_query")

    @property
    def event_type(self) -> str:
        """Returns the primary type of the update (e.g., 'message', 'callback_query')."""
        for key in ("message", "callback_query", "edited_message", "channel_post", "edited_channel_post"):
            if key in self.raw_update:
                return key
        return "unknown"

    @property
    def from_user(self) -> dict[str, Any] | None:
        """Extracts the user information (Sender)."""
        if self.message and "from" in self.message:
            return self.message["from"]
        if self.callback_query and "from" in self.callback_query:
            return self.callback_query["from"]
        if self.edited_message and "from" in self.edited_message:
            return self.edited_message["from"]
        return None

    @property
    def user_id(self) -> int | None:
        """Sender's unique ID."""
        user = self.from_user
        return user.get("id") if user else None

    @property
    def chat(self) -> dict[str, Any] | None:
        """Extracts the Chat object."""
        if self.message and "chat" in self.message:
            return self.message["chat"]
        if self.callback_query and "message" in self.callback_query:
            msg = self.callback_query["message"]
            if isinstance(msg, dict) and "chat" in msg:
                return msg["chat"]
        if self.edited_message and "chat" in self.edited_message:
            return self.edited_message["chat"]
        return None

    @property
    def chat_id(self) -> int | str | None:
        """Target chat identifier."""
        c = self.chat
        return c.get("id") if c else None

    @property
    def text(self) -> str | None:
        """Extracts text from message or callback_query data."""
        if self.message and "text" in self.message:
            return self.message["text"]
        if self.callback_query and "data" in self.callback_query:
            return self.callback_query["data"]
        return None

    @property
    def state(self) -> Any | None:
        """Access the active FSMContext bound to this session if FSM is enabled."""
        return self.data.get("state")

    # ==========================================
    # Contextual Shortcut Methods
    # ==========================================

    async def reply(
        self,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, Any]:
        """
        Send a message quoting the incoming message.

        :raises ValueError: If no chat_id can be resolved from context.
        """
        cid = self.chat_id
        if cid is None:
            raise ValueError("Cannot reply: chat_id not found in current update context.")

        msg_id: int | None = None
        if self.message and "message_id" in self.message:
            msg_id = self.message["message_id"]

        return await self.client.send_message(
            chat_id=cid,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            reply_to_message_id=msg_id,
            disable_web_page_preview=disable_web_page_preview,
            disable_notification=disable_notification,
        )

    async def send(
        self,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, Any]:
        """
        Send a message to the current chat without replying/quoting.

        :raises ValueError: If no chat_id can be resolved from context.
        """
        cid = self.chat_id
        if cid is None:
            raise ValueError("Cannot send: chat_id not found in current update context.")

        return await self.client.send_message(
            chat_id=cid,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
            disable_notification=disable_notification,
        )

    async def answer(
        self,
        text: str | None = None,
        show_alert: bool = False,
        url: str | None = None,
        cache_time: int | None = None,
    ) -> bool:
        """
        Answer an incoming callback query.

        :raises ValueError: If the current update is not a callback query.
        """
        cb = self.callback_query
        if not cb or "id" not in cb:
            raise ValueError("Cannot answer: current update is not a callback_query.")

        return await self.client.answer_callback_query(
            callback_query_id=str(cb["id"]),
            text=text,
            show_alert=show_alert,
            url=url,
            cache_time=cache_time,
        )

    def __repr__(self) -> str:
        return (
            f"BaleContext(update_id={self.update_id}, "
            f"event_type={self.event_type!r}, "
            f"user_id={self.user_id}, "
            f"chat_id={self.chat_id})"
        )
