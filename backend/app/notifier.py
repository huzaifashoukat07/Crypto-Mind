import logging

import httpx

from .config import settings

logger = logging.getLogger("notifier")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


async def send_telegram_message(text: str) -> bool:
    """Sends a message via the Telegram Bot API. Returns whether it succeeded.
    Never raises -- a notification failure (bad token, network blip, Telegram
    outage) must not be allowed to interrupt the trading loop."""
    if not is_configured():
        return False
    url = _TELEGRAM_API.format(token=settings.telegram_bot_token)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json={"chat_id": settings.telegram_chat_id, "text": text})
            response.raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("failed to send Telegram notification")
        return False
