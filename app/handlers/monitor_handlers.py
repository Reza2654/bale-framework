"""Handlers for URL monitoring, FSM multi-step registration, instant diagnostics, and deletion."""
from __future__ import annotations
import logging
from datetime import datetime
from framework.context.context import BaleContext
from framework.fsm.context import FSMContext
from framework.routing.filters.command import Command, CommandObject
from framework.routing.filters.state import StateFilter
from framework.routing.router import Router
from app.handlers.keyboards import (
    get_cancel_keyboard,
    get_delete_urls_inline,
    get_main_keyboard,
    get_skip_alias_keyboard,
    get_upgrade_inline,
)
from app.handlers.states import AddURLStates
from app.infrastructure.database import MonitorDatabase
from app.services.checker import check_url
from app.services.monitor_service import MonitorService

logger = logging.getLogger("bale.handlers.monitor")
monitor_router = Router("monitor")

# ----------------- Cancel Handler -----------------

@monitor_router.message(lambda ctx: ctx.text in ("❌ انصراف و بازگشت به منوی اصلی", "❌ انصراف", "/cancel"))
async def handle_cancel(ctx: BaleContext, state: FSMContext) -> None:
    await state.clear()
    await ctx.send(
        "عملیات لغو شد. به منوی اصلی بازگشتید.",
        reply_markup=get_main_keyboard(),
    )

# ----------------- Add URL Flow (FSM) -----------------

@monitor_router.message(lambda ctx: ctx.text == "➕ افزودن صفحه جدید" or ctx.text == "/add")
async def start_add_url(ctx: BaleContext, state: FSMContext, db: MonitorDatabase) -> None:
    user_id = ctx.user_id
    if user_id is None:
        return

    user = await db.get_or_create_user(user_id, ctx.chat_id)
    urls = await db.get_user_urls(user_id)
    plan = user.plan

    # Quota check
    if len(urls) >= plan.max_urls:
        quota_text = (
            "⚠️ <b>سقف سهمیه پلن شما تکمیل شده است!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"شما در حال حاضر <b>{len(urls)} از {plan.max_urls} صفحه</b> مجاز در <b>{plan.title}</b> را ثبت کرده‌اید.\n\n"
            "برای افزودن صفحات بیشتر می‌توانید یکی از صفحات قبلی را حذف کنید یا پلن خود را به <b>نقره‌ای (۱۰ صفحه)</b> یا <b>طلایی (۳۰ صفحه)</b> ارتقا دهید."
        )
        await ctx.send(
            text=quota_text,
            parse_mode="HTML",
            reply_markup=get_upgrade_inline(),
        )
        return

    await state.set_state(AddURLStates.waiting_for_url)
    msg = (
        "🔗 <b>لطفاً آدرس صفحه مورد نظر خود را ارسال کنید:</b>\n\n"
        "نمونه‌ها:\n"
        "• <code>https://myshop.ir/checkout</code>\n"
        "• <code>site.ir</code>\n\n"
        "💡 <i>پروتکل http یا https الزامی نیست و در صورت نبود، به صورت خودکار https اضافه می‌شود.</i>"
    )
    await ctx.send(text=msg, parse_mode="HTML", reply_markup=get_cancel_keyboard())

@monitor_router.message(StateFilter(AddURLStates.waiting_for_url))
async def process_url_input(ctx: BaleContext, state: FSMContext) -> None:
    raw_text = (ctx.text or "").strip()
    if not raw_text or " " in raw_text or "." not in raw_text:
        await ctx.send(
            "⚠️ فرمت آدرس وارد شده معتبر به نظر نمی‌رسد. لطفاً یک آدرس اینترنتی صحیح (مانند mysite.com) ارسال کنید:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    clean_url = raw_text
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    await state.update_data(target_url=clean_url)
    await state.set_state(AddURLStates.waiting_for_alias)

    await ctx.send(
        "🏷 <b>عالی! آیا می‌خواهید برای این صفحه یک نام دلخواه بگذارید؟</b>\n\n"
        "مثال: «صفحه سبد خرید»، «درگاه پرداخت»، «لندینگ کمپین»\n\n"
        "اگر نیازی ندارید، دکمه «⏩ رد کردن» را بزنید تا با همان آدرس لینک ذخیره شود:",
        parse_mode="HTML",
        reply_markup=get_skip_alias_keyboard(),
    )

@monitor_router.message(StateFilter(AddURLStates.waiting_for_alias))
async def process_alias_input(ctx: BaleContext, state: FSMContext, db: MonitorDatabase) -> None:
    user_id = ctx.user_id
    if user_id is None:
        return

    data = await state.get_data()
    target_url = data.get("target_url")
    if not target_url:
        await state.clear()
        await ctx.send("خطایی رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=get_main_keyboard())
        return

    raw_text = (ctx.text or "").strip()
    alias = ""
    if raw_text and not raw_text.startswith("⏩"):
        alias = raw_text

    await ctx.send("⏳ در حال بررسی اولیه اتصال به صفحه...", reply_markup=get_main_keyboard())

    # Perform initial immediate test
    test_result = await check_url(target_url)

    # Save to database
    new_url = await db.add_url(user_id=user_id, url=target_url, alias=alias)
    await db.update_check_result(new_url.id, test_result, datetime.now().isoformat(), was_up=True)
    await state.clear()

    status_badge = "🟢 در دسترس و سالم (کد 200)" if test_result.is_up else f"🔴 دارای اختلال ({test_result.status_code or 'تایم‌اوت'})"
    
    success_text = (
        "✅ <b>صفحه با موفقیت به سامانه مانیتورینگ اضافه شد!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷 <b>عنوان:</b> {alias or 'بدون عنوان'}\n"
        f"🔗 <b>آدرس:</b> <code>{target_url}</code>\n"
        f"📊 <b>وضعیت تست اولیه:</b> {status_badge}\n"
        f"⚡️ <b>زمان پاسخ:</b> {test_result.response_time_ms} میلی‌ثانیه\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>از این پس در صورت هرگونه قطعی یا خطا، فوراً پیام هشدار دریافت خواهید کرد.</i>"
    )

    if not test_result.is_up and test_result.failure_reason:
        success_text += f"\n\n🔍 <b>علت خطای اولیه:</b>\n{test_result.failure_reason}"

    await ctx.send(text=success_text, parse_mode="HTML", reply_markup=get_main_keyboard())

# ----------------- Status & Listing -----------------

@monitor_router.message(lambda ctx: ctx.text in ("📋 وضعیت زنده صفحات", "/status"))
async def handle_list_status(ctx: BaleContext, db: MonitorDatabase) -> None:
    user_id = ctx.user_id
    if user_id is None:
        return

    user = await db.get_or_create_user(user_id, ctx.chat_id)
    urls = await db.get_user_urls(user_id)

    if not urls:
        await ctx.send(
            "📭 شما هنوز هیچ صفحه‌ای برای پایش ثبت نکرده‌اید.\n\n"
            "با لمس دکمه «➕ افزودن صفحه جدید» اولین آدرس سایت خود را ثبت کنید.",
            reply_markup=get_main_keyboard(),
        )
        return

    up_count = sum(1 for u in urls if u.is_up)
    down_count = len(urls) - up_count

    report_lines = [
        "📊 <b>گزارش زنده وضعیت سلامت وب‌سایت شما</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🟢 صفحات سالم: <b>{up_count}</b> | 🔴 صفحات دارای ارور: <b>{down_count}</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    for idx, u in enumerate(urls, 1):
        if u.is_up:
            badge = "🟢 سالم"
            code_str = f"(کد {u.last_status_code or 200})"
            latency_str = f"⚡️ {u.last_response_time_ms or 0}ms"
            report_lines.append(f"{idx}. {badge} <b>{u.display_name}</b>\n   {code_str} | {latency_str}")
        else:
            badge = "🔴 قطعی / خطا"
            code_str = f"⚠️ کد {u.last_status_code}" if u.last_status_code else "⚠️ تایم‌اوت"
            report_lines.append(f"{idx}. {badge} <b>{u.display_name}</b>\n   {code_str}")
            if u.failure_reason:
                # Truncate reason if too long
                reason_short = u.failure_reason.split("\n")[0]
                report_lines.append(f"   🔍 <i>علت: {reason_short}</i>")

    report_lines.append("━━━━━━━━━━━━━━━━━━━━━")
    report_lines.append("🔄 <i>برای به‌روزرسانی لحظه‌ای، دکمه «⚡️ استعلام فوری» را لمس کنید.</i>")

    await ctx.send(text="\n".join(report_lines), parse_mode="HTML", reply_markup=get_main_keyboard())

# ----------------- Instant Check On-Demand -----------------

@monitor_router.message(lambda ctx: ctx.text in ("⚡️ استعلام فوری همین الان", "/check_now"))
async def handle_check_now(ctx: BaleContext, db: MonitorDatabase, monitor_service: MonitorService) -> None:
    user_id = ctx.user_id
    if user_id is None:
        return

    urls = await db.get_user_urls(user_id)
    if not urls:
        await ctx.send("شما هنوز هیچ صفحه‌ای اضافه نکرده‌اید.", reply_markup=get_main_keyboard())
        return

    await ctx.send("⚡️ در حال تست همزمان تمام صفحات شما... لطفاً چند ثانیه شکیبا باشید.")

    results = await monitor_service.check_user_now(user_id)

    report_lines = [
        "⚡️ <b>نتیجه استعلام لحظه‌ای تمام صفحات:</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    for u, res in results:
        if res.is_up:
            report_lines.append(
                f"🟢 <b>{u.display_name}</b>\n"
                f"   وضعیت: ۲۰۰ OK | زمان لود: {res.response_time_ms} میلی‌ثانیه"
            )
        else:
            status_text = f"کد {res.status_code}" if res.status_code else "عدم پاسخ (Timeout)"
            report_lines.append(
                f"🔴 <b>{u.display_name}</b>\n"
                f"   وضعیت: <b>{status_text}</b>\n"
                f"   علت احتمالی: {res.failure_reason or 'اختلال در اتصال'}"
            )
        report_lines.append("─────────────────────")

    report_lines.append(f"📅 زمان تست: {datetime.now().strftime('%H:%M:%S')}")

    await ctx.send(text="\n".join(report_lines), parse_mode="HTML", reply_markup=get_main_keyboard())

# ----------------- Delete Management -----------------

@monitor_router.message(lambda ctx: ctx.text in ("🗑 حذف و مدیریت صفحات", "/list"))
async def handle_manage_urls(ctx: BaleContext, db: MonitorDatabase) -> None:
    user_id = ctx.user_id
    if user_id is None:
        return

    urls = await db.get_user_urls(user_id)
    if not urls:
        await ctx.send("صفحه‌ای برای حذف وجود ندارد.", reply_markup=get_main_keyboard())
        return

    await ctx.send(
        "🗑 <b>روی هر صفحه‌ای که می‌خواهید از مانیتورینگ حذف شود کلیک کنید:</b>",
        parse_mode="HTML",
        reply_markup=get_delete_urls_inline(urls),
    )

@monitor_router.callback_query(lambda ctx: (ctx.text or "").startswith("del:"))
async def handle_delete_callback(ctx: BaleContext, db: MonitorDatabase) -> None:
    user_id = ctx.user_id
    data = ctx.text or ""
    try:
        url_id = int(data.split(":")[1])
        success = await db.delete_url(url_id, user_id)
        if success:
            await ctx.answer("صفحه با موفقیت حذف شد.", show_alert=True)
            # Update the list
            urls = await db.get_user_urls(user_id)
            if urls:
                await ctx.reply(
                    "لیست صفحات به‌روزرسانی شد:",
                    reply_markup=get_delete_urls_inline(urls),
                )
            else:
                await ctx.reply("تمام صفحات حذف شدند.", reply_markup=get_main_keyboard())
        else:
            await ctx.answer("صفحه یافت نشد یا قبلاً حذف شده است.", show_alert=True)
    except Exception as exc:
        logger.error("Error deleting URL: %s", exc)
        await ctx.answer("خطا در پردازش درخواست.", show_alert=True)

@monitor_router.callback_query(lambda ctx: ctx.text == "menu:back")
async def handle_back_callback(ctx: BaleContext) -> None:
    await ctx.answer()
    await ctx.send("به منوی اصلی بازگشتید.", reply_markup=get_main_keyboard())

# ----------------- Plan & Quotas -----------------

@monitor_router.message(lambda ctx: ctx.text in ("💎 پلن و سهمیه اشتراک", "/plan"))
async def handle_plan_info(ctx: BaleContext, db: MonitorDatabase) -> None:
    user_id = ctx.user_id
    if user_id is None:
        return

    user = await db.get_or_create_user(user_id, ctx.chat_id)
    urls = await db.get_user_urls(user_id)
    plan = user.plan

    plan_text = (
        "💎 <b>مشخصات پلن و اشتراک مانیتورینگ شما</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 سطح فعلی: <b>{plan.title}</b>\n"
        f"🌐 تعداد صفحات فعال: <b>{len(urls)} از {plan.max_urls} صفحه مجاز</b>\n"
        f"⏱ فواصل زمانی پایش خودکار: <b>{plan.interval_display}</b>\n"
        f"📝 توضیحات: <i>{plan.description}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>پلن‌های فعال سیستم مانیتورینگ:</b>\n"
        "• 🥉 <b>پلن پایه:</b> تا ۳ صفحه | بررسی هر ۱ روز (۲۴ ساعت)\n"
        "• 🥈 <b>پلن نقره‌ای:</b> تا ۱۰ صفحه | بررسی هر ۵ ساعت\n"
        "• 🥇 <b>پلن طلایی:</b> تا ۳۰ صفحه | بررسی فشرده هر ۱ ساعت\n"
        "• امکان ارسال هشدارها به گروه تیم فنی در بله\n"
        "• اولویت پایش در صف ورکرها"
    )

    await ctx.send(text=plan_text, parse_mode="HTML", reply_markup=get_upgrade_inline())

# ----------------- Support -----------------

@monitor_router.message(lambda ctx: ctx.text in ("❓ راهنما و پشتیبانی", "/support"))
async def handle_support(ctx: BaleContext) -> None:
    support_text = (
        "📞 <b>پشتیبانی و ارتباط با استودیو</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "در صورت بروز هرگونه سوال، درخواست مشاوره فنی، افزودن صفحات سفارشی یا ارتقای پلن اشتراک، با مدیریت در ارتباط باشید:\n\n"
        "👤 آیدی پشتیبانی در بله: @reza2654\n"
        "🌐 سایت رسمی: reza.biotechai.ir\n"
        "🤖 توسعه یافته بر بستر معماری <b>ExBaleBot</b>"
    )
    await ctx.send(text=support_text, parse_mode="HTML", reply_markup=get_main_keyboard())

# ----------------- Admin Commands -----------------

@monitor_router.message(Command("setplan"))
async def handle_admin_setplan(ctx: BaleContext, command: CommandObject, db: MonitorDatabase) -> None:
    """Admin command: /setplan <user_id> <plan_name> (base/silver/gold)"""
    args = (command.args or "").strip().split()
    if len(args) < 2:
        await ctx.send("دستور نامعتبر است. فرمت: <code>/setplan 123456789 gold</code>", parse_mode="HTML")
        return

    try:
        target_uid = int(args[0])
        plan_name = args[1].lower()
        if plan_name not in ("base", "silver", "gold"):
            await ctx.send("پلن نامعتبر است. انتخاب‌ها: base, silver, gold")
            return

        success = await db.set_user_plan(target_uid, plan_name)
        if success:
            await ctx.send(f"✅ پلن کاربر {target_uid} با موفقیت به {plan_name} ارتقا یافت.")
            try:
                await ctx.client.send_message(
                    chat_id=target_uid,
                    text=f"🎉 <b>تبریک!</b> پلن مانیتورینگ شما توسط پشتیبانی به <b>{plan_name}</b> ارتقا یافت.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        else:
            await ctx.send("کاربر یافت نشد.")
    except Exception as exc:
        await ctx.send(f"خطا در اجرای دستور: {exc}")
