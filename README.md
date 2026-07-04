# Crypto-Mind

A crypto trading bot with a web dashboard: pick a symbol (or a watchlist of
several), watch the live candlestick chart, click **Start Bot**, and it trades
automatically using a moving-average crossover strategy filtered by RSI.
Supports paper trading (simulated, zero risk), Binance testnet, and live
trading with real funds.

Give it more than one symbol and it runs in **scanner mode**: every tick it
evaluates the whole watchlist and automatically enters whichever symbols show
the strongest buy signal (most oversold RSI first), up to a configurable
number of concurrent open positions — so you don't have to pick the coin
yourself.

> ⚠️ **This is not financial advice, and past/simulated performance is not a
> guarantee of future results.** Trading carries real risk of financial loss.
> Start in paper mode, then testnet, before ever enabling live trading with
> real money. You are solely responsible for any funds you trade with.

## Architecture

- **`backend/`** — Python FastAPI service. Fetches OHLCV candles from Binance
  (via [ccxt](https://github.com/ccxt/ccxt)), runs the strategy, executes
  trades (paper/testnet/live), and streams live updates over a WebSocket.
- **`frontend/`** — React + TypeScript app (Vite). Renders the candlestick
  chart ([lightweight-charts](https://github.com/tradingview/lightweight-charts)),
  the bot control panel, position/PnL, and a live activity log.

## Strategy

The default and only bundled strategy is a **momentum MA-crossover filtered by
RSI** (`backend/app/strategy.py`):

- Buys when the fast SMA crosses above the slow SMA, *unless* RSI is already
  overbought (avoids chasing an extended move).
- Also buys on an RSI oversold reversal (RSI below the oversold threshold with
  price turning up).
- Sells when the fast SMA crosses below the slow SMA, or RSI becomes
  overbought while in a position.
- All periods/thresholds are configurable from the UI.

It's intentionally simple and readable so you can audit exactly what it does
before trusting it with money. `MaCrossoverRsiStrategy` is a small, self
contained class — swap in your own by following the same interface
(`evaluate(candles, in_position) -> StrategyOutput`).

## Optional ML confirmation filter

You can train a gradient-boosting classifier (`backend/ml/train.py`) to act as
a second-opinion gate on top of the base strategy: it predicts the probability
of an upward move from technical features (RSI, MACD, Bollinger %B/width,
volume ratio, momentum, volatility, MA gap), and a buy signal only proceeds if
that probability clears a confidence threshold.

**This is opt-in and off by default, and it does not guarantee better
results** — there is no model that reliably predicts crypto prices, and the
training script exists specifically so you can check that honestly before
trusting it:

```bash
cd backend
source .venv/bin/activate
python -m ml.train --symbol BTC/USDT --timeframe 5m --days 180
```

This fetches real historical candles, trains the model, and — the important
part — backtests the actual trading strategy on a held-out chronological
slice **both with and without the filter**, printing a side-by-side
comparison (total return, trade count, win rate). Only turn on **"Use ML
confirmation filter"** in the UI if the "with filter" numbers are actually
better than baseline on your own data; if they're not, the filter isn't
helping and you should leave it off. Try different `--horizon` /
`--up-threshold` / `--days` values — a single run isn't the final word.

Models are saved to `backend/ml/models/<SYMBOL>_<TIMEFRAME>.joblib` (one per
symbol+timeframe you train) and picked up automatically. Enabling the filter
for a symbol you haven't trained a model for doesn't block trading — the bot
logs a warning once and falls back to the base strategy signal alone for that
symbol.

## Telegram trade notifications

Get a message whenever the bot opens or closes a position:

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts — it gives you a bot token immediately.
2. Send any message to your new bot, then open in a browser:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   Find `"chat":{"id": ...}` in the response — that number is your chat ID.
3. Set both in `backend/.env`:
   ```
   TELEGRAM_BOT_TOKEN=<your token>
   TELEGRAM_CHAT_ID=<your chat id>
   ```
4. Restart the backend. In the UI, under **Notifications**, click **Send test message** to confirm it works before relying on it.

Each buy/sell sends a message with the symbol, quantity, price, reason for the trade, and (on exits) the realized PnL. Toggle **"Send a Telegram message whenever a position opens or closes"** off per-bot if you don't want it for a given run. A failed or slow Telegram delivery never blocks or delays trading — it's fire-and-forget.

## Safety rails

- **Mode gating**: `mode=live` requires both `ALLOW_LIVE_TRADING=true` in the
  backend's `.env` *and* an explicit `"I_UNDERSTAND_THE_RISK"` confirmation
  from the UI (a modal makes you type `I UNDERSTAND`). Either missing, and the
  request is rejected — this is a deliberate two-key lock.
- **Position sizing**: each entry only ever risks `position_size_pct` of
  available balance.
- **Stop-loss / take-profit**: checked every tick against the live price;
  triggers an immediate market sell.
- **Daily loss kill switch**: if realized PnL for the day drops below
  `-max_daily_loss_pct`, the bot stops itself (`status: stopped_kill_switch`)
  and will not trade again until manually restarted.
- **Paper mode never touches the exchange**: it only reads public market data
  and simulates fills/balances locally.

None of this makes live trading risk-free — it reduces the blast radius of a
strategy bug or a bad market move, it doesn't eliminate it.

## Running it locally

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit as needed
uvicorn app.main:app --reload --port 8000
```

For **paper mode** you don't need API keys — it only reads public Binance
market data. For **testnet** or **live** mode, set `BINANCE_API_KEY` /
`BINANCE_API_SECRET` in `.env` (for testnet, use keys generated from
https://testnet.binance.vision/). For **live**, also set
`ALLOW_LIVE_TRADING=true`.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE should point at the backend
npm run dev
```

Open the printed local URL (typically `http://localhost:5173`), pick a
symbol/timeframe/strategy params, choose a mode, and click **Start Bot**.

### Notes on network access

The backend needs outbound HTTPS access to `api.binance.com` (and
`testnet.binance.vision` for testnet mode). If you're running this inside a
sandboxed CI/dev container with an egress allowlist, make sure that host is
reachable, or the candle/chart fetches and bot loop will fail with a
`NetworkError`.

## Testing

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Unit tests cover the strategy's indicator math and signal logic
(`tests/test_strategy.py`), the paper broker's balance/PnL bookkeeping
(`tests/test_paper_broker.py`), the ML feature engineering
(`tests/test_features.py`), the trained-model loading/caching
(`tests/test_ml_filter.py`), and the Telegram notifier
(`tests/test_notifier.py`).

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/candles` | Fetch recent OHLCV candles for the chart |
| POST | `/api/bot/start` | Start a new bot instance with a given config |
| POST | `/api/bot/{id}/stop` | Stop a running bot |
| GET | `/api/bot/{id}` | Get a bot's current status/trades/PnL |
| GET | `/api/bots` | List all bot instances |
| GET | `/api/notifications/status` | Whether Telegram is configured on the server |
| POST | `/api/notifications/test` | Send a test Telegram message |
| GET | `/api/ml/models` | List symbol/timeframe pairs with a trained ML filter model |
| WS | `/ws` | Live stream of candle/trade/status/log events |

## Known limitations

- Spot trading only (no futures/margin, no multi-leg strategies).
- All watchlist symbols must share the same quote currency (e.g. all
  `*/USDT`) since the quote balance is a single shared pool across positions.
- One strategy shipped (MA crossover + RSI filter); adding more requires
  writing a new class in `strategy.py` and wiring it into `BotConfig`.
- `testnet`/`live` order fills are read directly from the exchange's order
  response; there's no reconciliation job if the process crashes mid-trade —
  check your exchange account directly if the bot stops unexpectedly while a
  position is open.
