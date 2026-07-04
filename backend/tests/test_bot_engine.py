import asyncio

from app.bot_engine import BotEngine
from app.schemas import BotConfig


def _engine():
    events = []
    config = BotConfig(symbols=["BTC/USDT"], mode="paper")
    engine = BotEngine("test-bot", config, on_event=events.append)
    return engine, events


def test_transient_failures_are_retried_below_threshold():
    engine, _ = _engine()
    for i in range(1, BotEngine.MAX_CONSECUTIVE_TICK_FAILURES):
        should_continue = engine._handle_tick_failure("connection blip")
        assert should_continue is True
        assert engine.status != "error"
        assert engine._consecutive_failures == i


def test_bot_stops_after_reaching_the_failure_threshold():
    # _handle_tick_failure fires a fire-and-forget Telegram notification via
    # asyncio.create_task on the final (fatal) failure, which requires a
    # running event loop -- exercise it the same way the real bot loop does.
    async def run():
        engine, events = _engine()
        for _ in range(BotEngine.MAX_CONSECUTIVE_TICK_FAILURES - 1):
            assert engine._handle_tick_failure("connection blip") is True

        should_continue = engine._handle_tick_failure("connection blip")

        assert should_continue is False
        assert engine.status == "error"
        assert "failed" in engine.last_error
        status_events = [e for e in events if e.type == "status"]
        assert status_events, "expected a status event to be emitted when the bot gives up"
        await asyncio.gather(*engine._background_tasks)

    asyncio.run(run())


def test_successful_tick_resets_the_failure_counter():
    engine, _ = _engine()
    engine._handle_tick_failure("connection blip")
    engine._handle_tick_failure("connection blip")
    assert engine._consecutive_failures == 2

    # Mirrors what _run() does after a successful _tick() call.
    engine._consecutive_failures = 0

    assert engine._consecutive_failures == 0
    assert engine.status != "error"
