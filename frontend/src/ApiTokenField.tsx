import { useState } from "react";
import { getApiToken, setApiToken } from "./auth";

export function ApiTokenField() {
  const [value, setValue] = useState(getApiToken());
  const [saving, setSaving] = useState(false);

  const save = () => {
    setApiToken(value.trim());
    setSaving(true);
    // Reload so the WebSocket and any in-flight state reconnect using the new token.
    setTimeout(() => window.location.reload(), 300);
  };

  return (
    <div className="api-token-field">
      <span>API token</span>
      <input
        type="password"
        value={value}
        placeholder="only needed for remote deployments"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && save()}
      />
      <button type="button" className="btn" onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
