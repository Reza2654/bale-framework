"""End-to-end integration test verifying the complete Uptime & Health Monitor Bot."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.domain.models import PLANS, CheckResult, User
from app.infrastructure.database import MonitorDatabase
from app.services.checker import check_url
from app.services.diagnostic import explain_exception, explain_status_code
from app.services.monitor_service import MonitorService, format_duration

async def run_tests() -> None:
    print("=== Testing Uptime & Health Monitor Bot ===")

    # 1. Test Diagnostic Explanations
    print("1. Testing Diagnostic Status Explanations...")
    assert "200 OK" in explain_status_code(200)
    assert "داخلی سرور" in explain_status_code(500)
    assert "Bad Gateway" in explain_status_code(502)
    assert "پیدا نشد" in explain_status_code(404)
    assert "دسترسی مسدود" in explain_status_code(403)
    print("   -> Diagnostics OK.")

    # 2. Test Exception Diagnostics
    print("2. Testing Exception Diagnostics...")
    timeout_title, timeout_desc = explain_exception(asyncio.TimeoutError("Timeout"))
    assert "تایم‌اوت" in timeout_title
    print(f"   -> Timeout Diagnostic: {timeout_title}")

    # 3. Test Duration Formatting
    print("3. Testing Duration Formatter...")
    assert format_duration(45) == "45 ثانیه"
    assert format_duration(150) == "2 دقیقه و 30 ثانیه"
    assert format_duration(3600) == "1 ساعت و 0 دقیقه"
    print("   -> Duration Formatter OK.")

    # 4. Test Database Layer & Quotas
    print("4. Testing Database Layer & Quotas...")
    test_db_path = Path("data/test_monitor.db")
    if test_db_path.exists():
        test_db_path.unlink()

    db = MonitorDatabase(test_db_path)
    user = await db.get_or_create_user(user_id=12345, chat_id="12345")
    assert user.user_id == 12345
    assert user.plan_name == "base"
    assert user.plan.max_urls == 3
    assert user.plan.check_interval_seconds == 86400
    assert user.plan.interval_display == "هر ۱ روز"

    # Add URL
    url1 = await db.add_url(user_id=12345, url="https://myshop.ir", alias="صفحه اصلی")
    assert url1.url == "https://myshop.ir"
    assert url1.alias == "صفحه اصلی"

    urls = await db.get_user_urls(12345)
    assert len(urls) == 1

    # Upgrade Plan to Silver (10 URLs, 5 hours check)
    await db.set_user_plan(12345, "silver")
    user_silver = await db.get_or_create_user(12345)
    assert user_silver.plan_name == "silver"
    assert user_silver.plan.max_urls == 10
    assert user_silver.plan.check_interval_seconds == 18000
    assert user_silver.plan.interval_display == "هر ۵ ساعت"

    # Simulate Status Check Update
    check_down = CheckResult(
        is_up=False,
        status_code=500,
        response_time_ms=250.0,
        failure_reason="خطای داخلی سرور",
    )
    now_str = "2026-11-10T12:00:00"
    await db.update_check_result(url1.id, check_down, now_str, was_up=True)

    urls_updated = await db.get_user_urls(12345)
    assert urls_updated[0].is_up is False
    assert urls_updated[0].last_status_code == 500
    assert urls_updated[0].failure_reason == "خطای داخلی سرور"

    # Simulate Recovery
    check_up = CheckResult(
        is_up=True,
        status_code=200,
        response_time_ms=120.0,
        failure_reason=None,
    )
    recovered_at = "2026-11-10T12:05:30"
    duration = await db.update_check_result(url1.id, check_up, recovered_at, was_up=False)
    assert duration == 330  # 5 mins 30 secs

    urls_recovered = await db.get_user_urls(12345)
    assert urls_recovered[0].is_up is True
    assert urls_recovered[0].last_status_code == 200

    # Upgrade Plan to Gold (30 URLs, 1 hour check)
    await db.set_user_plan(12345, "gold")
    user_upgraded = await db.get_or_create_user(12345)
    assert user_upgraded.plan_name == "gold"
    assert user_upgraded.plan.max_urls == 30
    assert user_upgraded.plan.check_interval_seconds == 3600
    assert user_upgraded.plan.interval_display == "هر ۱ ساعت"
    print("   -> Database & Plans & Downtime State Transitions OK.")

    # Clean up test db
    try:
        if test_db_path.exists():
            test_db_path.unlink()
    except Exception:
        pass

    print("\n✅ All End-to-End Tests Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
