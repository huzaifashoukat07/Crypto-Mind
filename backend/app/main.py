import logging

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .auth import check_ws_token, require_api_token
from .bot_manager import bot_manager
from .config import settings
from .exchange import ExchangeClient
from .ml_filter import list_available_models
from .notifier import is_configured as notifications_configured
from .notifier import send_telegram_message
from .schemas import BotStatus, StartBotRequest, TradingMode
from .ws_manager import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Crypto-Mind Trading Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/candles", dependencies=[Depends(require_api_token)])
async def get_candles(symbol: str = "BTC/USDT", timeframe: str = "5m", limit: int = 200):
    client = ExchangeClient(TradingMode.paper)
    try:
        candles = await client.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as exc:
        # Caught and re-raised as HTTPException (rather than left to propagate
        # as a bare 500) so CORS headers still get attached to the error
        # response -- Starlette only applies user middleware, including CORS,
        # to responses that flow through its normal exception handling, not
        # to an uncaught exception's default 500.
        logger.exception("failed to fetch candles")
        raise HTTPException(status_code=502, detail=str(exc))
    return [c.model_dump() for c in candles]


@app.post("/api/bot/start", response_model=BotStatus, dependencies=[Depends(require_api_token)])
async def start_bot(req: StartBotRequest):
    config = req.config
    if config.mode == TradingMode.live and not settings.allow_live_trading:
        raise HTTPException(
            status_code=403,
            detail=(
                "Live trading is disabled on this server. Set ALLOW_LIVE_TRADING=true "
                "in the backend .env to enable it. This is a deliberate safeguard."
            ),
        )
    if config.mode in (TradingMode.testnet, TradingMode.live) and (
        not settings.binance_api_key or not settings.binance_api_secret
    ):
        raise HTTPException(
            status_code=400,
            detail="BINANCE_API_KEY / BINANCE_API_SECRET are not configured on the server.",
        )
    return bot_manager.create_and_start(config)


@app.post("/api/bot/{bot_id}/stop", response_model=BotStatus, dependencies=[Depends(require_api_token)])
async def stop_bot(bot_id: str):
    try:
        return await bot_manager.stop(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="bot not found")


@app.get("/api/bot/{bot_id}", response_model=BotStatus, dependencies=[Depends(require_api_token)])
async def get_bot(bot_id: str):
    try:
        return bot_manager.get_status(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="bot not found")


@app.get("/api/bots", response_model=list[BotStatus], dependencies=[Depends(require_api_token)])
async def list_bots():
    return bot_manager.list_status()


@app.get("/api/ml/models", dependencies=[Depends(require_api_token)])
async def get_ml_models():
    return list_available_models()


@app.get("/api/notifications/status", dependencies=[Depends(require_api_token)])
async def get_notifications_status():
    return {"configured": notifications_configured()}


@app.post("/api/notifications/test", dependencies=[Depends(require_api_token)])
async def test_notification():
    if not notifications_configured():
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not configured on the server.",
        )
    ok = await send_telegram_message("Crypto-Mind: test notification. If you can read this, notifications are working.")
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to send via Telegram — check the bot token/chat ID and server logs.")
    return {"sent": True}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str | None = None):
    if not check_ws_token(token):
        await websocket.close(code=1008)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
