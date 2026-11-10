"""Common command handlers (/start, /help, /cancel)."""
from __future__ import annotations
import logging
from framework.context.context import BaleContext
from framework.fsm.context import FSMContext
from framework.routing.filters.command import Command
from framework.routing.router import Router
from app.handlers.keyboards import get_main_keyboard
from app.infrastructure.database import MonitorDatabase

logger = logging.getLogger("bale.handlers.common")
common_router = Router("common")

@common_router.message(Command("start"))
async def handle_start(ctx: BaleContext, state: FSMContext, db: MonitorDatabase) -> None:
    await state.clear()
    user_id = ctx.user_id
    if user_id is None:
        return

    user = await db.get_or_create_user(user_id, ctx.chat_id)
    urls = await db.get_user_urls(user_id)
    plan = user.plan

    welcome_text = (
        "👋 <b>سلام! به ربات هوشمند مانیتورینگ سلامت و آپ‌تایم سایت خوش آمدید.</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "این ربات به صورت ۲۴ ساعته صفحات وب‌سایت شما را پایش می‌کند و در صورت قطعی هاست، کندی شدید سرور یا بروز هرگونه خطای کدنویسی، <b>بلافاصله با ذکر علت دقیق</b> به شما هشدار می‌دهد.\n\n"
        f"📊 <b>مشخصات حساب شما:</b>\n"
        f"• سطح پلن: <b>{plan.title}</b>\n"
        f"• سقف مجاز صفحات: <b>{len(urls)} از {plan.max_urls} صفحه</b>\n"
        f"• بازه پایش خودکار: <b>{plan.interval_display}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "برای شروع، از دکمه‌های زیر استفاده کنید:"
    )

    await ctx.send(
        text=welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )

@common_router.message(Command("help"))
async def handle_help(ctx: BaleContext) -> None:
    help_text = (
        "📖 <b>راهنمای کار با ربات مانیتورینگ بات‌استودیو</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🔹 <b>➕ افزودن صفحه جدید:</b> آدرس صفحه مورد نظر (مانند صفحه اصلی، سبد خرید یا وبلاگ) را ثبت کنید.\n"
        "🔹 <b>📋 وضعیت زنده صفحات:</b> وضعیت فعلی تمام صفحات، پینگ و علت قطعی‌های اخیر را ببینید.\n"
        "🔹 <b>⚡️ استعلام فوری:</b> بدون معطلی در لحظه تمام صفحات شما تست شده و گزارش سلامت داده می‌شود.\n"
        "🔹 <b>🗑 حذف و مدیریت:</b> صفحات قدیمی یا غیرفعال خود را حذف کنید.\n"
        "🔹 <b>💎 پلن و سهمیه:</b> اطلاعات سهمیه صفحات و ارتقا به پایش ۱ دقیقه‌ای.\n\n"
        "💬 پشتیبانی و سفارش اختصاصی: @reza2654\n"
        "🌐 وب‌سایت: reza.biotechai.ir"
    )
    await ctx.send(text=help_text, parse_mode="HTML", reply_markup=get_main_keyboard())
