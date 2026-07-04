export type TradingMode = "paper" | "testnet" | "live";
export type OrderSide = "buy" | "sell";

export interface BotConfig {
  symbols: string[];
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
  max_concurrent_positions: number;
  poll_interval_sec: number;
  use_ml_filter: boolean;
  ml_confidence_threshold: number;
  live_confirmation?: "I_UNDERSTAND_THE_RISK" | null;
}

export interface MlModelInfo {
  symbol: string;
  timeframe: string;
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
  symbol: string;
  side: OrderSide;
  price: number;
  quantity: number;
  reason: string;
  pnl?: number | null;
}

export interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  unrealized_pnl: number;
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
  positions: Position[];
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
  symbols: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
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
  max_concurrent_positions: 3,
  poll_interval_sec: 5,
  use_ml_filter: false,
  ml_confidence_threshold: 0.55,
  live_confirmation: null,
};
