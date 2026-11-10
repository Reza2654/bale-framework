"""Application root router aggregating all domain sub-routers."""
from __future__ import annotations
from framework.routing.router import Router
from app.handlers.common import common_router
from app.handlers.monitor_handlers import monitor_router

root_router = Router("app_root")
root_router.include_router(common_router)
root_router.include_router(monitor_router)

__all__ = ["root_router"]
