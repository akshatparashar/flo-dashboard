import { useEffect, useState } from "react";
import { REFRESH_MS } from "../../api/hooks";
import { ago, clockIST } from "../../lib/format";
import { useLive } from "../../lib/live";

/** "Live · synced 12s ago" with a ring that fills until the next read. The red dot is the broadcast "on air" light;
 *  it turns amber when the server is serving an older copy and grey when the browser cannot reach the server. */
export function LiveStatus() {
  const live = useLive();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const synced = live.meta?.synced_at ?? null;
  const down = !!live.error && !live.meta;
  const stale = !!live.meta?.stale || !!live.error;
  const since = live.lastFetchAt ? Math.min(1, (now - live.lastFetchAt) / REFRESH_MS) : 0;
  const r = 6;
  const c = 2 * Math.PI * r;
  const cls = down ? "live is-down" : stale ? "live is-stale" : "live";
  const label = down ? "Offline" : stale ? "Delayed" : "Live";
  const title = down
    ? live.error ?? "Cannot reach the server"
    : `Sheets last read at ${clockIST(synced)} IST. The dashboard checks for new data every minute.${live.meta?.stale ? " Google did not answer the last read, so the previous copy is shown." : ""}`;
  return (
    <div className={cls} title={title} aria-live="polite">
      <span className="dot" aria-hidden="true" />
      <b>{label}</b>
      <span className="label-long">{live.fetching ? "syncing…" : synced ? `synced ${ago(synced, now)}` : "connecting…"}</span>
      <svg className="ring" viewBox="0 0 16 16" aria-hidden="true">
        <circle className="track" cx="8" cy="8" r={r} />
        <circle className="bar" cx="8" cy="8" r={r} strokeDasharray={c} strokeDashoffset={c * (1 - since)} />
      </svg>
    </div>
  );
}
