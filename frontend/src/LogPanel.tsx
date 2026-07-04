interface LogLine {
  time: number;
  message: string;
}

export function LogPanel({ lines }: { lines: LogLine[] }) {
  return (
    <div className="log-panel">
      <h3>Activity log</h3>
      <div className="log-lines">
        {lines.length === 0 && <div className="log-empty">No activity yet.</div>}
        {lines
          .slice()
          .reverse()
          .map((line, i) => (
            <div className="log-line" key={`${line.time}-${i}`}>
              <span className="log-time">
                {new Date(line.time * 1000).toLocaleTimeString()}
              </span>
              <span>{line.message}</span>
            </div>
          ))}
      </div>
    </div>
  );
}
