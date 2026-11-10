"""Diagnostic analyzer for translating HTTP status codes and exceptions into actionable Persian explanations."""
from __future__ import annotations

HTTP_STATUS_EXPLANATIONS: dict[int, str] = {
    # 2xx Success
    200: "✅ صفحه سالم است و وب‌سرور بدون مشکل پاسخ داد (200 OK).",
    
    # 3xx Redirections
    301: "🔄 ریدایرکت دائم (Moved Permanently) - آدرس صفحه به نشانی دیگری منتقل شده است.",
    302: "🔄 ریدایرکت موقت (Found/Redirect) - صفحه به نشانی موقت ارجاع داده شد.",
    307: "🔄 هدایت موقت با حفظ متد (Temporary Redirect).",
    308: "🔄 هدایت دائم با حفظ متد (Permanent Redirect).",

    # 4xx Client Errors
    400: "⚠️ درخواست نامعتبر (Bad Request) - سرور ساختار درخواست را متوجه نشد.",
    401: "🔒 نیاز به احراز هویت (Unauthorized) - ورود به این بخش نیازمند نام‌کاربری و رمز عبور است.",
    403: "🚫 دسترسی مسدود است (Forbidden) - فایروال هاست، سیستم ضداسپم یا WAF/کلودفلر مانع باز شدن صفحه شده است.",
    404: "🔍 صفحه پیدا نشد (Not Found) - این آدرس وجود ندارد، حذف شده یا پیوند یکتا در وردپرس تغییر کرده است.",
    405: "⚠️ متد غیرمجاز (Method Not Allowed) - ارسال متد با این آدرس هماهنگ نیست.",
    408: "⏱ مهلت درخواست به پایان رسید (Request Timeout) - قبل از رسیدن داده‌ها، ارتباط قطع شد.",
    429: "🛑 محدودیت تعداد درخواست (Too Many Requests) - سایت تحت بار ترافیکی شدید است و آی‌پی موقتاً لیمیت شده است.",

    # 5xx Server Errors
    500: "🔥 خطای داخلی سرور (Internal Server Error) - خرابی فایل‌های کدهای PHP/پایتون، اختلال در اتصال دیتابیس یا تداخل افزونه‌ها.",
    502: "⚡️ خطای درگاه وب‌سرور (Bad Gateway) - وب‌سرور (Nginx/LiteSpeed) نمی‌تواند با پردازشگر اسکریپت (PHP-FPM/Backend) ارتباط بگیرد.",
    503: "🛑 سرویس موقتاً از دسترس خارج است (Service Unavailable) - هاست بیش از حد پر شده، رم/CPU تمام شده یا در حالت تعمیر است.",
    504: "⏱ تایم‌اوت پاسخ وب‌سرور (Gateway Timeout) - سرور برای اجرای کوئری‌ها یا پردازش سایت زمان زیادی تلف کرد و متوقف شد.",
}

def explain_status_code(status_code: int | None) -> str:
    """Returns a user-friendly Persian explanation of the HTTP status code."""
    if status_code is None:
        return "❌ پاسخی از سرور دریافت نشد."
    
    if status_code in HTTP_STATUS_EXPLANATIONS:
        return HTTP_STATUS_EXPLANATIONS[status_code]
    
    if 200 <= status_code < 300:
        return f"✅ پاسخ موفق ({status_code})."
    if 300 <= status_code < 400:
        return f"🔄 ارجاع و تغییر مسیر به آدرس دیگر ({status_code})."
    if 400 <= status_code < 500:
        return f"⚠️ خطای درخواست یا دسترسی سمت کلاینت ({status_code})."
    if status_code >= 500:
        return f"🔥 خطای شدید سمت سرور میزبان یا دیتابیس ({status_code})."
    
    return f"وضعیت نامشخص ({status_code})."

def explain_exception(exc: Exception) -> tuple[str, str]:
    """
    Analyzes a Python/HTTPX exception and returns:
    (short_reason_title, detailed_persian_explanation)
    """
    exc_name = type(exc).__name__
    exc_str = str(exc).lower()

    if "timeout" in exc_str or "timeouterror" in exc_name.lower():
        return (
            "⏱ عدم پاسخ و تایم‌اوت سرور (Connection Timeout)",
            "سرور سایت در مهلت مقرر (۱۰ ثانیه) هیچ پاسخی ارسال نکرد. احتمالاً هاست قطع است، پورت مسدود است یا ترافیک غیرعادی وجود دارد.",
        )
    
    if "connecterror" in exc_name.lower() or "connection refused" in exc_str:
        return (
            "🔌 قطعی کامل اتصال به سرور (Connection Refused)",
            "ارتباط با وب‌سرور برقرار نشد؛ ممکن است وب‌سرور آپاچی/انجین‌ایکس خاموش باشد یا پورت ۸۰/۴۴۳ فیلتر شده باشد.",
        )

    if "name resolution" in exc_str or "gaierror" in exc_str or "dns" in exc_str:
        return (
            "🌐 خطای DNS و عدم شناسایی دامنه (DNS Resolution Failed)",
            "دی‌ان‌اس‌های دامنه سایت پاسخ نمی‌دهند یا تاریخ انقضای دامنه فرا رسیده و ثبت‌کننده دامنه را غیرفعال کرده است.",
        )

    if "ssl" in exc_str or "cert" in exc_str:
        return (
            "🔒 خطای گواهی امنیتی SSL (SSL Certificate Error)",
            "گواهی امنیتی HTTPS منقضی شده، با نام دامنه همخوانی ندارد یا به درستی روی سرور کانفیگ نشده است.",
        )

    return (
        f"❌ خطای شبکه ({exc_name})",
        f"در حین اتصال به سایت خطای سیستمی رخ داد: {str(exc)[:150]}",
    )
