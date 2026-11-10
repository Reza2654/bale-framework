"""Application entrypoint for the Website Uptime & Health Monitor Bot built with ExBaleBot."""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from framework.client.client import BaleBotClient
from framework.dispatcher.dispatcher import Dispatcher
from framework.fsm.storage.sqlite import SqliteStorage
from framework.ingestion.polling import LongPollingEngine
from framework.middlewares.error_boundary import ErrorBoundaryMiddleware
from framework.middlewares.logging import LoggingMiddleware
from framework.middlewares.rate_limit import RateLimitMiddleware
from framework.tasks.scheduler import IntervalScheduler
from app.handlers import root_router
from app.infrastructure.database import MonitorDatabase
from app.services.monitor_service import MonitorService

# Setup structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bale.main")

async def main() -> None:
    logger.info("Initializing Website Uptime & Health Monitor Bot (ExBaleBot)...")

    # 1. Initialize API Client
    client = BaleBotClient(
        token=settings.BALE_BOT_TOKEN,
        base_url=settings.BASE_URL,
    )

    # 2. Setup Persistent FSM Storage (SQLite)
    fsm_db_path = Path("data/fsm.db")
    fsm_db_path.parent.mkdir(parents=True, exist_ok=True)
    storage = SqliteStorage(fsm_db_path)

    # 3. Setup Business Database & Core Services
    db = MonitorDatabase(settings.DB_PATH)
    monitor_service = MonitorService(db=db, client=client)

    # 4. Setup Central Dispatcher with Dependency Injection
    dp = Dispatcher(
        client=client,
        storage=storage,
        workflow_data={
            "db": db,
            "monitor_service": monitor_service,
        },
    )

    # 5. Register Middlewares
    dp.add_middleware(LoggingMiddleware())
    dp.add_middleware(ErrorBoundaryMiddleware(send_fallback_message=True))
    dp.add_middleware(RateLimitMiddleware(rate=5, per_seconds=1.0))

    # 6. Mount Root Application Router
    dp.include_router(root_router)

    # 7. Setup Background Interval Scheduler for Periodic Health Checks
    scheduler = IntervalScheduler()
    scheduler.add_job(
        name="periodic_website_monitor",
        interval_seconds=float(settings.SCHEDULER_INTERVAL_SECS),
        callback=monitor_service.execute_periodic_cycle,
        run_immediately=True,
    )
    scheduler.start()
    logger.info("Background monitor scheduler started (interval: %ds).", settings.SCHEDULER_INTERVAL_SECS)

    # 8. Setup Resilient Long-Polling Ingestion Engine
    engine = LongPollingEngine(
        client=client,
        consumer=dp,
        workers_count=settings.WORKERS_COUNT,
        poll_timeout=20,
        drop_pending_updates=False,
    )

    try:
        # Check bot identity
        if settings.BALE_BOT_TOKEN and "YOUR_BALE" not in settings.BALE_BOT_TOKEN:
            try:
                me = await client.get_me()
                logger.info("Connected to Bale API as: @%s (ID: %s)", me.get("username"), me.get("id"))
            except Exception as e:
                logger.warning("Could not fetch bot identity: %s (will continue)", e)
        else:
            logger.warning("No valid BALE_BOT_TOKEN configured in .env. Bot is running in offline/dry-run mode.")

        logger.info("Starting Long-Polling engine. Bot is now online and monitoring!")
        await engine.run_until_stopped()

    finally:
        logger.info("Graceful shutdown initiated...")
        await scheduler.stop()
        await client.close()
        logger.info("Bot shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process terminated.")
