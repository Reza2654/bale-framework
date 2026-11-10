"""Content type filter for matching message media and payload types."""

from __future__ import annotations

from typing import Any

from framework.context.context import BaleContext
from framework.routing.filters.base import BaseFilter


class ContentTypeFilter(BaseFilter):
    """
    Matches incoming messages based on the presence of specific content types.

    Supported types: 'text', 'photo', 'document', 'audio', 'video', 'voice', 'contact', 'location'
    """

    def __init__(self, *types: str) -> None:
        self.types = set(types)

    async def __call__(self, event: BaleContext) -> bool:
        msg = event.message
        if not msg:
            return False

        for content_type in self.types:
            if content_type in msg:
                return True

        return False
