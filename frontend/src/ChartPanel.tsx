import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Candle, Trade } from "./types";

interface Props {
  symbol: string;
  candles: Candle[];
  trades: Trade[];
}

const ZOOM_IN_FACTOR = 0.7;
const ZOOM_OUT_FACTOR = 1 / ZOOM_IN_FACTOR;

export function ChartPanel({ symbol, candles, trades }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const fittedSymbolRef = useRef<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "var(--chart-text)",
      },
      grid: {
        vertLines: { color: "var(--chart-grid)" },
        horzLines: { color: "var(--chart-grid)" },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current || candles.length === 0) return;
    candleSeriesRef.current.setData(
      candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    const markers = trades.map((t) => ({
      time: t.time as UTCTimestamp,
      position: (t.side === "buy" ? "belowBar" : "aboveBar") as "belowBar" | "aboveBar",
      color: t.side === "buy" ? "#26a69a" : "#ef5350",
      shape: (t.side === "buy" ? "arrowUp" : "arrowDown") as "arrowUp" | "arrowDown",
      text: `${t.side.toUpperCase()} ${t.price.toFixed(2)}`,
    }));
    // v5 API: markers are set via a plugin primitive, but the simple setMarkers
    // helper still exists on the series in lightweight-charts 5.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (candleSeriesRef.current as any).setMarkers?.(markers);

    // Only reset the view the first time this symbol's data loads (or when
    // switching to a different symbol) -- otherwise every live candle update
    // (every few seconds while the bot runs) would snap any zoom/pan the user
    // did back to fitContent(), which is exactly the "zoom keeps resetting"
    // bug this guards against.
    if (fittedSymbolRef.current !== symbol) {
      fittedSymbolRef.current = symbol;
      chartRef.current?.timeScale().fitContent();
    }
  }, [symbol, candles, trades]);

  const zoom = (factor: number) => {
    const timeScale = chartRef.current?.timeScale();
    const range = timeScale?.getVisibleLogicalRange();
    if (!timeScale || !range) return;
    const center = (range.from + range.to) / 2;
    const halfWidth = ((range.to - range.from) / 2) * factor;
    timeScale.setVisibleLogicalRange({ from: center - halfWidth, to: center + halfWidth });
  };

  return (
    <div className="chart-panel-wrap">
      <div ref={containerRef} className="chart-panel" />
      <div className="chart-zoom-controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoom(ZOOM_IN_FACTOR)}>
          +
        </button>
        <button type="button" aria-label="Zoom out" onClick={() => zoom(ZOOM_OUT_FACTOR)}>
          −
        </button>
        <button type="button" aria-label="Reset zoom" onClick={() => chartRef.current?.timeScale().fitContent()}>
          ⤢
        </button>
      </div>
    </div>
  );
}
