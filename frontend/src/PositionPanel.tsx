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
  const totalUnrealized = status.positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);

  return (
    <div className="position-panel">
      <h3>Position</h3>
      <div className="stat-grid">
        <div className="stat">
          <span className="stat-label">Quote balance</span>
          <span className="stat-value">{fmt(status.balance_quote)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Unrealized PnL</span>
          <span className={`stat-value ${pnlClass(totalUnrealized)}`}>{fmt(totalUnrealized)}</span>
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

      {status.positions.length > 0 ? (
        <table className="positions-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Unrealized</th>
            </tr>
          </thead>
          <tbody>
            {status.positions.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td>
                <td>{fmt(p.quantity, 6)}</td>
                <td>{fmt(p.entry_price)}</td>
                <td className={pnlClass(p.unrealized_pnl)}>{fmt(p.unrealized_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="log-empty" style={{ marginTop: 10 }}>
          No open positions — waiting for a signal.
        </div>
      )}

      {status.last_error && <div className="error-banner">{status.last_error}</div>}
    </div>
  );
}
