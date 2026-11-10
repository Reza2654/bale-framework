"""Domain entities and data models for the Website Uptime & Health Monitor Bot."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

def to_persian_digits(val: int | str) -> str:
    """Converts English digits to Persian digits."""
    return str(val).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def format_plan_interval(seconds: int) -> str:
    """Formats check interval into human-readable Persian text."""
    if seconds >= 86400:
        days = seconds // 86400
        p_days = to_persian_digits(days)
        return f"هر {p_days} روز"
    if seconds >= 3600:
        hours = seconds // 3600
        p_hours = to_persian_digits(hours)
        return f"هر {p_hours} ساعت"
    mins = seconds // 60
    p_mins = to_persian_digits(mins)
    return f"هر {p_mins} دقیقه"

@dataclass
class Plan:
    name: str                        # "base", "silver", "gold"
    title: str                       # "🥉 پلن پایه", "🥈 پلن نقره‌ای", "🥇 پلن طلایی"
    max_urls: int                    # 3, 10, 30
    check_interval_seconds: int      # 86400 (1 day), 18000 (5 hours), 3600 (1 hour)
    description: str

    @property
    def interval_display(self) -> str:
        return format_plan_interval(self.check_interval_seconds)

PLANS: dict[str, Plan] = {
    "base": Plan(
        name="base",
        title="🥉 پلن پایه",
        max_urls=3,
        check_interval_seconds=86400,  # هر ۱ روز (۲۴ ساعت)
        description="پایش تا ۳ صفحه، بررسی خودکار هر ۱ روز (۲۴ ساعت)، اعلان فوری قطعی و گزارش وضعیت",
    ),
    "silver": Plan(
        name="silver",
        title="🥈 پلن نقره‌ای",
        max_urls=10,
        check_interval_seconds=18000,  # هر ۵ ساعت
        description="پایش تا ۱۰ صفحه، بررسی خودکار هر ۵ ساعت، اعلان قطعی و ریکاوری، محاسبه پینگ و مدت قطعی",
    ),
    "gold": Plan(
        name="gold",
        title="🥇 پلن طلایی",
        max_urls=30,
        check_interval_seconds=3600,   # هر ۱ ساعت
        description="پایش تا ۳۰ صفحه، بررسی فشرده هر ۱ ساعت، اولویت بالای پایش در صف ورکرها و گزارش‌گیری جامع",
    ),
}

@dataclass
class User:
    user_id: int
    plan_name: str = "base"
    notify_chat_id: int | str | None = None
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def plan(self) -> Plan:
        return PLANS.get(self.plan_name, PLANS["base"])

@dataclass
class MonitoredURL:
    id: int
    user_id: int
    url: str
    alias: str = ""
    last_status_code: int | None = None
    last_response_time_ms: float | None = None
    last_checked_at: str | None = None
    is_up: bool = True
    failure_reason: str | None = None
    downtime_started_at: str | None = None
    is_active: bool = True

    @property
    def display_name(self) -> str:
        if self.alias and self.alias.strip():
            return f"{self.alias} ({self.url})"
        return self.url

@dataclass
class CheckResult:
    is_up: bool
    status_code: int | None
    response_time_ms: float | None
    failure_reason: str | None
    details: str = ""
