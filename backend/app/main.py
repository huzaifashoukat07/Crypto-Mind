import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .bot_manager import bot_manager
from .config import settings
from .exchange import ExchangeClient
from .schemas import BotStatus, StartBotRequest, TradingMode
from .ws_manager import ws_manager

logging.basicConfig(level=logging.INFO)

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


@app.get("/api/candles")
async def get_candles(symbol: str = "BTC/USDT", timeframe: str = "5m", limit: int = 200):
    client = ExchangeClient(TradingMode.paper)
    candles = await client.fetch_ohlcv(symbol, timeframe, limit=limit)
    return [c.model_dump() for c in candles]


@app.post("/api/bot/start", response_model=BotStatus)
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


@app.post("/api/bot/{bot_id}/stop", response_model=BotStatus)
async def stop_bot(bot_id: str):
    try:
        return await bot_manager.stop(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="bot not found")


@app.get("/api/bot/{bot_id}", response_model=BotStatus)
async def get_bot(bot_id: str):
    try:
        return bot_manager.get_status(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="bot not found")


@app.get("/api/bots", response_model=list[BotStatus])
async def list_bots():
    return bot_manager.list_status()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
