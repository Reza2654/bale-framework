"""Type-safe callback data pack/unpack and routing filter."""

from __future__ import annotations

from typing import Any, ClassVar, get_type_hints

from framework.context.context import BaleContext
from framework.routing.filters.base import BaseFilter


class CallbackDataFilter(BaseFilter):
    """Filter that matches and deserializes callback data against a CallbackData schema."""

    def __init__(self, callback_type: type[CallbackData], **expected_values: Any) -> None:
        self.callback_type = callback_type
        self.expected_values = expected_values

    async def __call__(self, event: BaleContext) -> bool | dict[str, Any]:
        if not event.callback_query:
            return False

        raw_data = event.callback_query.get("data")
        if not raw_data:
            return False

        try:
            instance = self.callback_type.unpack(raw_data)
        except (ValueError, TypeError):
            return False

        # Verify any expected parameter values
        for key, expected_val in self.expected_values.items():
            if getattr(instance, key, None) != expected_val:
                return False

        return {"callback_data": instance}


class CallbackData:
    """
    Base class for type-safe callback data serialization and matching.

    Usage:
        class ProductAction(CallbackData, prefix="prod"):
            action: str
            product_id: int

        # Pack:
        data_str = ProductAction(action="buy", product_id=12).pack()
        # -> "prod:buy:12"

        # Route matching:
        @router.callback_query(ProductAction.filter(action="buy"))
        async def on_buy(ctx: BaleContext, callback_data: ProductAction):
            ...
    """

    __prefix__: ClassVar[str] = ""
    __sep__: ClassVar[str] = ":"

    def __init_subclass__(cls, prefix: str, sep: str = ":", **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not prefix:
            raise ValueError("CallbackData subclass must specify a non-empty 'prefix'.")
        if sep in prefix:
            raise ValueError(f"Prefix {prefix!r} cannot contain separator {sep!r}")
        cls.__prefix__ = prefix
        cls.__sep__ = sep

    @classmethod
    def _get_fields(cls) -> list[str]:
        """Return declared instance field names excluding class-level metadata."""
        type_hints = get_type_hints(cls)
        return [k for k in type_hints if not k.startswith("_")]

    def __init__(self, **kwargs: Any) -> None:
        field_names = self._get_fields()
        for name in field_names:
            if name in kwargs:
                setattr(self, name, kwargs[name])
            else:
                setattr(self, name, None)

    def pack(self) -> str:
        """Serialize schema fields into a delimited string within 64 bytes."""
        parts = [self.__class__.__prefix__]
        sep = self.__class__.__sep__
        for name in self._get_fields():
            val = getattr(self, name, None)
            if val is None:
                parts.append("")
            elif isinstance(val, bool):
                parts.append("1" if val else "0")
            else:
                parts.append(str(val))

        packed = sep.join(parts)
        byte_len = len(packed.encode("utf-8"))
        if byte_len > 64:
            raise ValueError(
                f"Serialized callback data exceeds 64 bytes limit ({byte_len} bytes): {packed!r}"
            )
        return packed

    @classmethod
    def unpack(cls, raw: str) -> CallbackData:
        """Deserialize raw callback string into a strongly-typed instance."""
        parts = raw.split(cls.__sep__)
        if not parts or parts[0] != cls.__prefix__:
            raise ValueError(f"Prefix mismatch for {cls.__name__}: expected {cls.__prefix__!r}")

        field_names = cls._get_fields()
        type_hints = get_type_hints(cls)
        values = parts[1:]

        if len(values) != len(field_names):
            raise ValueError(
                f"Field count mismatch for {cls.__name__}: expected {len(field_names)}, got {len(values)}"
            )

        kwargs: dict[str, Any] = {}
        for name, raw_val in zip(field_names, values):
            target_type = type_hints.get(name, str)
            if raw_val == "":
                kwargs[name] = None
            elif target_type is bool:
                kwargs[name] = raw_val in ("1", "True", "true")
            elif target_type in (int, float, str):
                kwargs[name] = target_type(raw_val)
            else:
                kwargs[name] = raw_val

        return cls(**kwargs)

    @classmethod
    def filter(cls, **expected_values: Any) -> CallbackDataFilter:
        """Create a route filter predicate matching this callback data schema."""
        return CallbackDataFilter(cls, **expected_values)

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={getattr(self, k)!r}" for k in self._get_fields())
        return f"{self.__class__.__name__}({attrs})"
