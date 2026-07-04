import { useEffect, useState } from "react";
import { api } from "./api";
import type { BotConfig, BotRunStatus, MlModelInfo, TradingMode } from "./types";

interface Props {
  config: BotConfig;
  onChange: (config: BotConfig) => void;
  onStart: () => void;
  onStop: () => void;
  status: BotRunStatus | null;
  busy: boolean;
}

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

function NumberField({
  label,
  value,
  step = 1,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  step?: number;
  onChange: (v: number) => void;
  disabled: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function SymbolsField({
  value,
  onChange,
  disabled,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  disabled: boolean;
}) {
  const [raw, setRaw] = useState(value.join(", "));

  useEffect(() => {
    setRaw(value.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.join(",")]);

  const commit = (text: string) => {
    const parsed = text
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (parsed.length > 0) onChange(parsed);
  };

  return (
    <label className="field" style={{ flex: 2, minWidth: 200 }}>
      <span>Watchlist (comma-separated)</span>
      <input
        value={raw}
        disabled={disabled}
        placeholder="BTC/USDT, ETH/USDT, SOL/USDT"
        onChange={(e) => setRaw(e.target.value)}
        onBlur={(e) => commit(e.target.value)}
      />
    </label>
  );
}

export function ControlPanel({ config, onChange, onStart, onStop, status, busy }: Props) {
  const [showLiveConfirm, setShowLiveConfirm] = useState(false);
  const [mlModels, setMlModels] = useState<MlModelInfo[]>([]);
  const isRunning = status === "running" || status === "starting";
  const set = <K extends keyof BotConfig>(key: K, value: BotConfig[K]) =>
    onChange({ ...config, [key]: value });
  const isScannerMode = config.symbols.length > 1;

  useEffect(() => {
    api.mlModels().then(setMlModels).catch(() => setMlModels([]));
  }, []);

  const trainedSymbolsForTimeframe = mlModels
    .filter((m) => m.timeframe === config.timeframe && config.symbols.includes(m.symbol))
    .map((m) => m.symbol);
  const untrainedSymbols = config.symbols.filter((s) => !trainedSymbolsForTimeframe.includes(s));

  const handleStartClick = () => {
    if (config.mode === "live" && config.live_confirmation !== "I_UNDERSTAND_THE_RISK") {
      setShowLiveConfirm(true);
      return;
    }
    onStart();
  };

  return (
    <div className="control-panel">
      <div className="field-row">
        <SymbolsField value={config.symbols} onChange={(v) => set("symbols", v)} disabled={isRunning} />
        <label className="field">
          <span>Timeframe</span>
          <select
            value={config.timeframe}
            disabled={isRunning}
            onChange={(e) => set("timeframe", e.target.value)}
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Mode</span>
          <select
            value={config.mode}
            disabled={isRunning}
            onChange={(e) => {
              const mode = e.target.value as TradingMode;
              onChange({ ...config, mode, live_confirmation: null });
            }}
          >
            <option value="paper">Paper (simulated)</option>
            <option value="testnet">Testnet</option>
            <option value="live">Live (real funds)</option>
          </select>
        </label>
      </div>
      {isScannerMode && (
        <p className="hint-text">
          Scanner mode: watching {config.symbols.length} symbols. Each tick, the bot evaluates
          all of them and automatically enters whichever show the strongest buy signal (most
          oversold RSI first), up to {config.max_concurrent_positions} open position
          {config.max_concurrent_positions === 1 ? "" : "s"} at a time.
        </p>
      )}

      <fieldset className="field-group" disabled={isRunning}>
        <legend>Strategy — MA crossover filtered by RSI</legend>
        <div className="field-row">
          <NumberField label="Fast MA period" value={config.fast_period} onChange={(v) => set("fast_period", v)} disabled={isRunning} />
          <NumberField label="Slow MA period" value={config.slow_period} onChange={(v) => set("slow_period", v)} disabled={isRunning} />
          <NumberField label="RSI period" value={config.rsi_period} onChange={(v) => set("rsi_period", v)} disabled={isRunning} />
        </div>
        <div className="field-row">
          <NumberField label="RSI overbought" value={config.rsi_overbought} onChange={(v) => set("rsi_overbought", v)} disabled={isRunning} />
          <NumberField label="RSI oversold" value={config.rsi_oversold} onChange={(v) => set("rsi_oversold", v)} disabled={isRunning} />
          <NumberField label="Poll interval (s)" value={config.poll_interval_sec} onChange={(v) => set("poll_interval_sec", v)} disabled={isRunning} />
        </div>
      </fieldset>

      <fieldset className="field-group" disabled={isRunning}>
        <legend>Capital &amp; risk management</legend>
        <div className="field-row">
          <NumberField label="Starting balance (paper)" value={config.starting_balance} onChange={(v) => set("starting_balance", v)} disabled={isRunning} />
          <NumberField label="Position size %" value={config.position_size_pct} onChange={(v) => set("position_size_pct", v)} disabled={isRunning} />
          <NumberField label="Max concurrent positions" value={config.max_concurrent_positions} onChange={(v) => set("max_concurrent_positions", v)} disabled={isRunning} />
        </div>
        <div className="field-row">
          <NumberField label="Stop loss %" value={config.stop_loss_pct} step={0.1} onChange={(v) => set("stop_loss_pct", v)} disabled={isRunning} />
          <NumberField label="Take profit %" value={config.take_profit_pct} step={0.1} onChange={(v) => set("take_profit_pct", v)} disabled={isRunning} />
          <NumberField label="Max daily loss % (kill switch)" value={config.max_daily_loss_pct} step={0.5} onChange={(v) => set("max_daily_loss_pct", v)} disabled={isRunning} />
        </div>
      </fieldset>

      <fieldset className="field-group" disabled={isRunning}>
        <legend>ML confirmation filter (optional)</legend>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={config.use_ml_filter}
            onChange={(e) => set("use_ml_filter", e.target.checked)}
          />
          <span>Require a trained ML model to also confirm buy signals</span>
        </label>
        {config.use_ml_filter && (
          <>
            <div className="field-row" style={{ marginTop: 8 }}>
              <NumberField
                label="Confidence threshold"
                value={config.ml_confidence_threshold}
                step={0.01}
                onChange={(v) => set("ml_confidence_threshold", v)}
                disabled={isRunning}
              />
            </div>
            <p className="hint-text">
              {trainedSymbolsForTimeframe.length > 0
                ? `Trained model found for: ${trainedSymbolsForTimeframe.join(", ")} (${config.timeframe}).`
                : "No trained models found for this timeframe yet."}
              {untrainedSymbols.length > 0 &&
                ` No model for ${untrainedSymbols.join(", ")} — those symbols will trade on the base strategy alone until you train one (see README: backend/ml/train.py).`}
            </p>
          </>
        )}
      </fieldset>

      <div className="start-row">
        {!isRunning ? (
          <button className="btn btn-start" onClick={handleStartClick} disabled={busy}>
            {busy ? "Starting…" : "Start Bot"}
          </button>
        ) : (
          <button className="btn btn-stop" onClick={onStop} disabled={busy}>
            {busy ? "Stopping…" : "Stop Bot"}
          </button>
        )}
        {status && <span className={`status-pill status-${status}`}>{status}</span>}
      </div>

      {showLiveConfirm && (
        <div className="modal-backdrop" onClick={() => setShowLiveConfirm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Confirm live trading</h3>
            <p>
              You are about to start the bot in <strong>LIVE</strong> mode. It will place
              real market orders on your Binance account using real funds, following the
              strategy and risk parameters above. Losses are possible and are not
              reversible.
            </p>
            <p>Type <code>I UNDERSTAND</code> to confirm.</p>
            <ConfirmInput
              onConfirmed={() => {
                onChange({ ...config, live_confirmation: "I_UNDERSTAND_THE_RISK" });
                setShowLiveConfirm(false);
                onStart();
              }}
              onCancel={() => setShowLiveConfirm(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function ConfirmInput({ onConfirmed, onCancel }: { onConfirmed: () => void; onCancel: () => void }) {
  const [text, setText] = useState("");
  return (
    <div className="confirm-input">
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="I UNDERSTAND" />
      <div className="modal-actions">
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
        <button
          className="btn btn-danger"
          disabled={text.trim().toUpperCase() !== "I UNDERSTAND"}
          onClick={onConfirmed}
        >
          Start live trading
        </button>
      </div>
    </div>
  );
}
