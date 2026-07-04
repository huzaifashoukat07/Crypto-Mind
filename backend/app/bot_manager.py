import uuid

from .bot_engine import BotEngine
from .schemas import BotConfig, BotStatus
from .ws_manager import ws_manager


class BotManager:
    def __init__(self):
        self._bots: dict[str, BotEngine] = {}

    def create_and_start(self, config: BotConfig) -> BotStatus:
        bot_id = uuid.uuid4().hex[:12]
        engine = BotEngine(bot_id, config, on_event=ws_manager.broadcast)
        self._bots[bot_id] = engine
        engine.start()
        return engine.to_status()

    async def stop(self, bot_id: str) -> BotStatus:
        engine = self._get(bot_id)
        await engine.stop()
        return engine.to_status()

    def get_status(self, bot_id: str) -> BotStatus:
        return self._get(bot_id).to_status()

    def list_status(self) -> list[BotStatus]:
        return [b.to_status() for b in self._bots.values()]

    def _get(self, bot_id: str) -> BotEngine:
        if bot_id not in self._bots:
            raise KeyError(f"unknown bot id {bot_id}")
        return self._bots[bot_id]


bot_manager = BotManager()
