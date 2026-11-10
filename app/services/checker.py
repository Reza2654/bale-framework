"""Async HTTP health checker for evaluating website status and response times."""
from __future__ import annotations
import logging
import time
from typing import Any
import httpx
from app.domain.models import CheckResult
from app.services.diagnostic import explain_exception, explain_status_code

logger = logging.getLogger("bale.monitor.checker")

# Realistic User-Agent to prevent bot-blocking firewalls (Cloudflare, LiteSpeed, etc.)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 ExBaleBot-Monitor/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa,en;q=0.9",
}

async def check_url(
    url: str,
    timeout_seconds: float = 12.0,
    follow_redirects: bool = True,
    verify_ssl: bool = False, # Often in Iran intranet or staging, SSL check needs tolerance
) -> CheckResult:
    """
    Asynchronously checks a single target URL.
    Returns a CheckResult containing status, latency in ms, and diagnostics.
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    start_time = time.perf_counter()
    timeout = httpx.Timeout(timeout_seconds, connect=6.0)

    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=follow_redirects,
            verify=verify_ssl,
        ) as client:
            response = await client.get(clean_url)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 1)

            status_code = response.status_code
            is_up = (200 <= status_code < 400) # 2xx and valid 3xx are considered alive; non-200 can be flagged

            # If user explicitly wants 200 only, we can consider strictly 200:
            strictly_200 = (status_code == 200)

            reason = explain_status_code(status_code)

            return CheckResult(
                is_up=strictly_200,
                status_code=status_code,
                response_time_ms=elapsed_ms,
                failure_reason=None if strictly_200 else reason,
                details=f"کد وضعیت {status_code} در {elapsed_ms} میلی‌ثانیه دریافت شد.",
            )

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 1)
        short_title, full_explanation = explain_exception(exc)
        logger.warning("Check failed for %s: %s (after %.1fms)", clean_url, exc, elapsed_ms)

        return CheckResult(
            is_up=False,
            status_code=None,
            response_time_ms=elapsed_ms,
            failure_reason=f"{short_title}\n💡 {full_explanation}",
            details=str(exc)[:120],
        )
