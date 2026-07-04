import type { BotConfig, BotStatus, Candle, MlModelInfo } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  candles: (symbol: string, timeframe: string, limit = 200) =>
    fetch(
      `${API_BASE}/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`
    ).then((r) => json<Candle[]>(r)),

  startBot: (config: BotConfig) =>
    fetch(`${API_BASE}/api/bot/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    }).then((r) => json<BotStatus>(r)),

  stopBot: (botId: string) =>
    fetch(`${API_BASE}/api/bot/${botId}/stop`, { method: "POST" }).then((r) =>
      json<BotStatus>(r)
    ),

  getBot: (botId: string) =>
    fetch(`${API_BASE}/api/bot/${botId}`).then((r) => json<BotStatus>(r)),

  mlModels: () => fetch(`${API_BASE}/api/ml/models`).then((r) => json<MlModelInfo[]>(r)),
};
