"""Keyboard markups (Reply & Inline) for the Uptime Monitor Bot."""
from __future__ import annotations
from typing import Any
from app.domain.models import MonitoredURL

def get_main_keyboard() -> dict[str, Any]:
    """Returns the persistent main reply keyboard."""
    return {
        "keyboard": [
            [{"text": "📋 وضعیت زنده صفحات"}, {"text": "⚡️ استعلام فوری همین الان"}],
            [{"text": "➕ افزودن صفحه جدید"}, {"text": "🗑 حذف و مدیریت صفحات"}],
            [{"text": "💎 پلن و سهمیه اشتراک"}, {"text": "❓ راهنما و پشتیبانی"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

def get_cancel_keyboard() -> dict[str, Any]:
    """Reply keyboard for cancelling active operations."""
    return {
        "keyboard": [
            [{"text": "❌ انصراف و بازگشت به منوی اصلی"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }

def get_skip_alias_keyboard() -> dict[str, Any]:
    """Reply keyboard offering to skip adding an alias."""
    return {
        "keyboard": [
            [{"text": "⏩ رد کردن نام دلخواه (ثبت فقط با آدرس)"}],
            [{"text": "❌ انصراف"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }

def get_delete_urls_inline(urls: list[MonitoredURL]) -> dict[str, Any]:
    """Inline keyboard for picking a URL to delete."""
    inline_keyboard = []
    for u in urls:
        label = f"🗑 {u.alias or u.url[:25]}"
        inline_keyboard.append([{"text": label, "callback_data": f"del:{u.id}"}])

    inline_keyboard.append([{"text": "🔙 بازگشت", "callback_data": "menu:back"}])
    return {"inline_keyboard": inline_keyboard}

def get_upgrade_inline() -> dict[str, Any]:
    """Inline keyboard to contact support for plan upgrade."""
    return {
        "inline_keyboard": [
            [{"text": "🚀 ارتقای پلن به نقره‌ای یا طلایی", "url": "https://ble.ir/reza2654"}],
            [{"text": "🌐 مشاهده تعرفه‌ها در سایت", "url": "http://reza.biotechai.ir/products.html"}],
        ]
    }
