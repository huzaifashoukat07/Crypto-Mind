import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import { ApiTokenField } from "./ApiTokenField";
import { ChartPanel } from "./ChartPanel";
import { ControlPanel } from "./ControlPanel";
import { LogPanel } from "./LogPanel";
import { PositionPanel } from "./PositionPanel";
import { api } from "./api";
import { useBotSocket } from "./useBotSocket";
import { DEFAULT_CONFIG } from "./types";
import type { BotConfig, BotStatus, Candle, WsEvent } from "./types";

interface LogLine {
  time: number;
  message: string;
}

export default function App() {
  const [config, setConfig] = useState<BotConfig>(DEFAULT_CONFIG);
  const [chartSymbol, setChartSymbol] = useState(config.symbols[0]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const botIdRef = useRef<string | null>(null);

  const isRunning = status?.status === "running" || status?.status === "starting";
  // While a bot is running, chart symbol choices come from its own config
  // (locked in at start); otherwise they follow whatever is being edited.
  const watchlist = isRunning ? status!.config.symbols : config.symbols;

  useEffect(() => {
    if (!watchlist.includes(chartSymbol)) {
      setChartSymbol(watchlist[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchlist.join(",")]);

  // Load a chart preview for the currently viewed symbol whenever it (or the
  // timeframe) changes and no bot is running yet to stream live candles instead.
  useEffect(() => {
    if (isRunning) return;
    let cancelled = false;
    api
      .candles(chartSymbol, config.timeframe)
      .then((data) => {
        if (!cancelled) setCandles(data);
      })
      .catch((err) => {
        if (!cancelled) setErrorBanner(String(err.message ?? err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartSymbol, config.timeframe, isRunning]);

  const handleEvent = useCallback(
    (event: WsEvent) => {
      if (botIdRef.current && event.bot_id !== botIdRef.current) return;

      if (event.type === "candle") {
        const { symbol, ...candle } = event.data as unknown as Candle & { symbol: string };
        if (symbol !== chartSymbol) return;
        setCandles((prev) => {
          const idx = prev.findIndex((c) => c.time === candle.time);
          if (idx === -1) return [...prev, candle];
          const next = prev.slice();
          next[idx] = candle;
          return next;
        });
      } else if (event.type === "status") {
        setStatus(event.data as unknown as BotStatus);
      } else if (event.type === "log") {
        const data = event.data as unknown as LogLine;
        setLogLines((prev) => [...prev, data]);
      } else if (event.type === "error") {
        const data = event.data as unknown as { message: string };
        setErrorBanner(data.message);
      }
    },
    [chartSymbol]
  );

  useBotSocket(handleEvent);

  const handleStart = async () => {
    setBusy(true);
    setErrorBanner(null);
    try {
      const result = await api.startBot(config);
      botIdRef.current = result.id;
      setStatus(result);
      setLogLines([]);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    if (!botIdRef.current) return;
    setBusy(true);
    try {
      const result = await api.stopBot(botIdRef.current);
      setStatus(result);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const chartTrades = (status?.trades ?? []).filter((t) => t.symbol === chartSymbol);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Crypto-Mind</h1>
        <span className="subtitle">Chart-driven crypto trading bot</span>
        <ApiTokenField />
      </header>

      {errorBanner && (
        <div className="error-banner top-banner" onClick={() => setErrorBanner(null)}>
          {errorBanner}
        </div>
      )}

      <main className="app-body">
        <section className="chart-section">
          <div className="chart-toolbar">
            <span>Viewing chart for</span>
            <select value={chartSymbol} onChange={(e) => setChartSymbol(e.target.value)}>
              {watchlist.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <ChartPanel symbol={chartSymbol} candles={candles} trades={chartTrades} />
        </section>
        <aside className="side-panel">
          <ControlPanel
            config={config}
            onChange={setConfig}
            onStart={handleStart}
            onStop={handleStop}
            status={status?.status ?? null}
            busy={busy}
          />
          <PositionPanel status={status} />
          <LogPanel lines={logLines} />
        </aside>
      </main>
    </div>
  );
}
