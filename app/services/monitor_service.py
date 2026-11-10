"""Core monitoring orchestration service for periodic and on-demand URL checking."""
from __future__ import annotations
import asyncio
from datetime import datetime
import logging
from typing import TYPE_CHECKING
from app.domain.models import CheckResult, MonitoredURL, User
from app.infrastructure.database import MonitorDatabase
from app.services.checker import check_url

if TYPE_CHECKING:
    from framework.client.client import BaleBotClient

logger = logging.getLogger("bale.monitor.service")

def format_duration(seconds: int) -> str:
    """Formats duration in seconds into a friendly Persian string."""
    if seconds < 60:
        return f"{seconds} ثانیه"
    minutes = seconds // 60
    rem_seconds = seconds % 60
    if minutes < 60:
        return f"{minutes} دقیقه و {rem_seconds} ثانیه" if rem_seconds else f"{minutes} دقیقه"
    hours = minutes // 60
    rem_minutes = minutes % 60
    return f"{hours} ساعت و {rem_minutes} دقیقه"

class MonitorService:
    def __init__(self, db: MonitorDatabase, client: BaleBotClient, concurrency_limit: int = 20) -> None:
        self.db = db
        self.client = client
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def execute_periodic_cycle(self) -> None:
        """Executed periodically by the IntervalScheduler to monitor all due URLs."""
        try:
            targets = await self.db.get_all_active_targets()
            if not targets:
                return

            now = datetime.now()
            due_targets: list[tuple[MonitoredURL, User]] = []

            for url_obj, user_obj in targets:
                plan_interval = user_obj.plan.check_interval_seconds
                if not url_obj.last_checked_at:
                    due_targets.append((url_obj, user_obj))
                    continue

                try:
                    last_check_dt = datetime.fromisoformat(url_obj.last_checked_at)
                    elapsed = (now - last_check_dt).total_seconds()
                    if elapsed >= plan_interval:
                        due_targets.append((url_obj, user_obj))
                except Exception:
                    due_targets.append((url_obj, user_obj))

            if not due_targets:
                return

            logger.info("Executing monitoring cycle for %d due targets...", len(due_targets))

            tasks = [self._check_and_notify_single(url_obj, user_obj) for url_obj, user_obj in due_targets]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as exc:
            logger.exception("Error during monitoring cycle: %s", exc)

    async def _check_and_notify_single(self, url_obj: MonitoredURL, user_obj: User) -> None:
        async with self.semaphore:
            now_iso = datetime.now().isoformat()
            was_up = url_obj.is_up

            # 1. Perform HTTP check
            check = await check_url(url_obj.url)

            # 2. Update database & calculate resolved downtime if recovered
            duration_seconds = await self.db.update_check_result(
                url_id=url_obj.id,
                check=check,
                now_iso=now_iso,
                was_up=was_up,
            )

            # 3. Handle Alert Dispatching
            chat_id = user_obj.notify_chat_id or user_obj.user_id

            # Case A: Transitioned from UP to DOWN (ALERT)
            if was_up and not check.is_up:
                time_str = datetime.now().strftime("%H:%M:%S")
                status_display = str(check.status_code) if check.status_code else "عدم پاسخ (Timeout)"
                
                alert_text = (
                    "🚨 <b>هشدار قطعی در وب‌سایت شما!</b>\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"🌐 <b>صفحه:</b> {url_obj.display_name}\n"
                    f"🔗 <b>آدرس:</b> {url_obj.url}\n"
                    f"⚠️ <b>کد وضعیت:</b> {status_display}\n\n"
                    f"🔍 <b>علت احتمالی:</b>\n{check.failure_reason}\n\n"
                    f"⏱ <b>زمان پاسخ:</b> {check.response_time_ms} میلی‌ثانیه\n"
                    f"📅 <b>زمان ثبت خطا:</b> {time_str}\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    "💡 <i>ربات مانیتورینگ بات‌استودیو فوراً وضعیت را زیر نظر دارد.</i>"
                )
                try:
                    await self.client.send_message(
                        chat_id=chat_id,
                        text=alert_text,
                        parse_mode="HTML",
                    )
                    logger.info("Downtime alert sent to chat %s for %s", chat_id, url_obj.url)
                except Exception as e:
                    logger.error("Failed to send downtime alert to %s: %s", chat_id, e)

            # Case B: Transitioned from DOWN to UP (RECOVERY)
            elif not was_up and check.is_up:
                time_str = datetime.now().strftime("%H:%M:%S")
                duration_str = format_duration(duration_seconds or 60)

                recovery_text = (
                    "✅ <b>صفحه با موفقیت به حالت عادی برگشت!</b>\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"🌐 <b>صفحه:</b> {url_obj.display_name}\n"
                    f"🔗 <b>آدرس:</b> {url_obj.url}\n"
                    f"⏱ <b>مدت زمان کل قطعی:</b> <b>{duration_str}</b>\n"
                    f"⚡️ <b>زمان پاسخ فعلی:</b> {check.response_time_ms} میلی‌ثانیه\n"
                    f"📅 <b>زمان ریکاوری:</b> {time_str}\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    "🟢 <i>سایت مجدداً آنلاین و پاسخ‌گوی کاربران شماست.</i>"
                )
                try:
                    await self.client.send_message(
                        chat_id=chat_id,
                        text=recovery_text,
                        parse_mode="HTML",
                    )
                    logger.info("Recovery alert sent to chat %s for %s", chat_id, url_obj.url)
                except Exception as e:
                    logger.error("Failed to send recovery alert to %s: %s", chat_id, e)

    async def check_user_now(self, user_id: int) -> list[tuple[MonitoredURL, CheckResult]]:
        """Instant on-demand check of all URLs belonging to a user."""
        urls = await self.db.get_user_urls(user_id)
        if not urls:
            return []

        now_iso = datetime.now().isoformat()
        results: list[tuple[MonitoredURL, CheckResult]] = []

        async def _check_one(u: MonitoredURL) -> tuple[MonitoredURL, CheckResult]:
            res = await check_url(u.url)
            await self.db.update_check_result(u.id, res, now_iso, u.is_up)
            return (u, res)

        results = await asyncio.gather(*[_check_one(u) for u in urls])
        return list(results)
