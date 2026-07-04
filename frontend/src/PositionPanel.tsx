import type { BotStatus } from "./types";

function fmt(n: number, digits = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function PositionPanel({ status }: { status: BotStatus | null }) {
  if (!status) {
    return (
      <div className="position-panel">
        <h3>Position</h3>
        <div className="log-empty">Start the bot to see live balance and PnL.</div>
      </div>
    );
  }

  const pnlClass = (v: number) => (v > 0 ? "pnl-pos" : v < 0 ? "pnl-neg" : "");

  return (
    <div className="position-panel">
      <h3>Position</h3>
      <div className="stat-grid">
        <div className="stat">
          <span className="stat-label">Quote balance</span>
          <span className="stat-value">{fmt(status.balance_quote)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Base position</span>
          <span className="stat-value">{fmt(status.balance_base, 6)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Entry price</span>
          <span className="stat-value">{status.entry_price ? fmt(status.entry_price) : "—"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Unrealized PnL</span>
          <span className={`stat-value ${pnlClass(status.unrealized_pnl)}`}>{fmt(status.unrealized_pnl)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Realized PnL</span>
          <span className={`stat-value ${pnlClass(status.realized_pnl)}`}>{fmt(status.realized_pnl)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Daily PnL</span>
          <span className={`stat-value ${pnlClass(status.daily_pnl)}`}>{fmt(status.daily_pnl)}</span>
        </div>
      </div>
      {status.last_error && <div className="error-banner">{status.last_error}</div>}
    </div>
  );
}
