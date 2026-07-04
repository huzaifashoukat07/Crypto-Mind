export type TradingMode = "paper" | "testnet" | "live";
export type OrderSide = "buy" | "sell";

export interface BotConfig {
  symbol: string;
  timeframe: string;
  mode: TradingMode;
  fast_period: number;
  slow_period: number;
  rsi_period: number;
  rsi_overbought: number;
  rsi_oversold: number;
  starting_balance: number;
  position_size_pct: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_daily_loss_pct: number;
  poll_interval_sec: number;
  live_confirmation?: "I_UNDERSTAND_THE_RISK" | null;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Trade {
  time: number;
  side: OrderSide;
  price: number;
  quantity: number;
  reason: string;
  pnl?: number | null;
}

export type BotRunStatus =
  | "starting"
  | "running"
  | "stopped"
  | "error"
  | "stopped_kill_switch";

export interface BotStatus {
  id: string;
  config: BotConfig;
  status: BotRunStatus;
  balance_quote: number;
  balance_base: number;
  position_qty: number;
  entry_price: number | null;
  unrealized_pnl: number;
  realized_pnl: number;
  daily_pnl: number;
  trades: Trade[];
  last_error: string | null;
}

export interface WsEvent {
  type: "candle" | "trade" | "status" | "log" | "error";
  bot_id: string;
  data: Record<string, unknown>;
}

export const DEFAULT_CONFIG: BotConfig = {
  symbol: "BTC/USDT",
  timeframe: "5m",
  mode: "paper",
  fast_period: 9,
  slow_period: 21,
  rsi_period: 14,
  rsi_overbought: 70,
  rsi_oversold: 30,
  starting_balance: 1000,
  position_size_pct: 25,
  stop_loss_pct: 2,
  take_profit_pct: 4,
  max_daily_loss_pct: 5,
  poll_interval_sec: 5,
  live_confirmation: null,
};
