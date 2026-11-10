"""Command filter for matching /command patterns with argument extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from framework.context.context import BaleContext
from framework.routing.filters.base import BaseFilter


@dataclass(frozen=True, slots=True)
class CommandObject:
    """Parsed command structure containing the command name, prefix, and trailing arguments."""

    prefix: str
    command: str
    mention: str | None
    args: str | None


class Command(BaseFilter):
    """
    Matches incoming text messages starting with a command prefix.

    Usage:
        @router.message(Command("start"))
        @router.message(Command("help", "info", prefix="/"))
    """

    def __init__(self, *commands: str, prefix: str = "/", ignore_case: bool = True) -> None:
        self.commands = set(c.lower() if ignore_case else c for c in commands)
        self.prefix = prefix
        self.ignore_case = ignore_case

        # Regex matching: prefix + command + optional @botmention + whitespace + optional args
        escaped_prefix = re.escape(self.prefix)
        self._pattern = re.compile(
            rf"^{escaped_prefix}(?P<command>[\w\d_]+)(?:@(?P<mention>[\w\d_]+))?(?:\s+(?P<args>.*))?$",
            re.IGNORECASE if self.ignore_case else 0,
        )

    async def __call__(self, event: BaleContext) -> bool | dict[str, Any]:
        text = event.text
        if not text or not event.message:
            return False

        match = self._pattern.match(text.strip())
        if not match:
            return False

        parsed_command = match.group("command")
        if self.ignore_case:
            parsed_command = parsed_command.lower()

        if self.commands and parsed_command not in self.commands:
            return False

        cmd_obj = CommandObject(
            prefix=self.prefix,
            command=parsed_command,
            mention=match.group("mention"),
            args=match.group("args"),
        )
        return {"command": cmd_obj}
