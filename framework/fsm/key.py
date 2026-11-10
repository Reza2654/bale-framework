"""Storage key for state isolation in FSM."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StorageKey:
    """
    Hashable composite key defining the isolation boundary for FSM states and data.

    Ensures that user states in private chats do not collide with their states
    in groups or channels, and multi-bot environments remain isolated.
    """

    bot_id: int | str
    chat_id: int | str
    user_id: int | str

    def to_string(self) -> str:
        """Serialize key into a colon-separated string."""
        return f"{self.bot_id}:{self.chat_id}:{self.user_id}"

    @classmethod
    def from_string(cls, value: str) -> StorageKey:
        """Deserialize key from a colon-separated string."""
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid StorageKey format: {value!r}")
        return cls(bot_id=parts[0], chat_id=parts[1], user_id=parts[2])
