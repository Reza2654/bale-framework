# Bale Bot Application Framework

A universal, modular, and production-ready application framework for bots built on the **Bale Messenger** platform (`https://tapi.bale.ai`), adhering to Clean / Hexagonal Architecture principles.

---

## 🏛 Architecture Overview

```
                      [ INGESTION LAYER ]
               ┌─────────────────────────────────┐
               │ LongPollingEngine / Webhook     │
               └───────────────┬─────────────────┘
                               │ Raw Update
                               ▼
 ═══════════════════════════════════════════════════════════════════════
                      [ CORE FRAMEWORK ]
               ┌─────────────────────────────────┐
               │       Dispatcher Engine         │
               └───────────────┬─────────────────┘
                               ▼
               ┌─────────────────────────────────┐
               │      Middleware Pipeline        │
               │  - Logging & Trace ID           │
               │  - Rate Limiter (Sliding Window)│
               │  - Unit of Work (Transactions)  │
               │  - Error Boundary               │
               └───────────────┬─────────────────┘
                               ▼
               ┌─────────────────────────────────┐
               │    Routing Engine & FSM         │
               │  (Command, Callback, State)     │
               └───────────────┬─────────────────┘
 ═══════════════════════════════════════════════════════════════════════
                      [ DOMAIN & SERVICES ]
                               ▼
               ┌─────────────────────────────────┐
               │        Domain Handlers          │
               │  (ctx, state, uow, command)     │
               └───────────────┬─────────────────┘
                               ▼
               ┌─────────────────────────────────┐
               │  TaskExecutor & Scheduler       │
               └─────────────────────────────────┘
```

---

## 🚀 Quickstart Example

```python
import asyncio
from framework.client import BaleBotClient
from framework.dispatcher import Dispatcher
from framework.fsm import FSMContext, State, StatesGroup, SqliteStorage
from framework.ingestion import LongPollingEngine
from framework.middlewares import ErrorBoundaryMiddleware, LoggingMiddleware, RateLimitMiddleware
from framework.routing import Command, CommandObject, Router, StateFilter


# 1. Define FSM States
class Onboarding(StatesGroup):
    waiting_for_name = State()


# 2. Build Feature Router
router = Router("onboarding")


@router.message(Command("start"))
async def cmd_start(ctx, command: CommandObject, state: FSMContext):
    await state.set_state(Onboarding.waiting_for_name)
    await ctx.reply(f"Hello! Please tell me your name (ref: {command.args}):")


@router.message(StateFilter(Onboarding.waiting_for_name))
async def process_name(ctx, state: FSMContext):
    await state.update_data(name=ctx.text)
    await state.clear()
    await ctx.reply(f"Welcome aboard, {ctx.text}!")


# 3. Assemble Application
async def main():
    client = BaleBotClient(token="YOUR_BALE_BOT_TOKEN")
    storage = SqliteStorage("fsm_data.db")

    dp = Dispatcher(client=client, storage=storage)
    dp.add_middleware(LoggingMiddleware())
    dp.add_middleware(RateLimitMiddleware(rate=5, period=1.0))
    dp.add_middleware(ErrorBoundaryMiddleware())
    dp.include_router(router)

    engine = LongPollingEngine(
        client=client,
        consumer=dp,
        workers_count=8,
        drop_pending_updates=True,
    )

    await engine.run_until_stopped()


if __name__ == "__main__":
    asyncio.run(main())
```
