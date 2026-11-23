import gsap from "gsap";
import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import type { SourceStatus } from "../api/types";
import { ago } from "../lib/format";
import { useLive } from "../lib/live";
import { prefersReducedMotion, useWidth } from "./charts/common";

const ORDER = ["tracker", "sample_summary", "overview_fabricators", "fabric_po", "target_revenue", "flo_future", "vendor_rate", "in_out_sale"];
const LABEL: Record<string, string> = {
  tracker: "Master sheet",
  sample_summary: "Sample summary",
  overview_fabricators: "Fabricator report",
  fabric_po: "Fabric PO",
  target_revenue: "Designer target",
  flo_future: "FLO Future",
  vendor_rate: "Vendor rates",
  in_out_sale: "In/Out sale",
};

export interface FlowOut {
  label: string;
  value: string;
  to: string;
  hot?: boolean;
}

/** The sheets wired into FLO and out to what they drive. Wires are real: one per Google Sheet, red and broken when
 *  that sheet fails. Sparks travel only when the browser actually asks for data (sources -> core) and when an
 *  answer arrives (core -> outputs); a brighter burst marks a sheet whose data really changed. */
export function DataFlow({ sources, outputs, now }: { sources: Record<string, SourceStatus> | undefined; outputs: FlowOut[]; now: number }) {
  const [wrap, width] = useWidth<HTMLDivElement>();
  const svg = useRef<SVGSVGElement>(null);
  const live = useLive();
  const narrow = width > 0 && width < 720;

  const L = useMemo(() => {
    const W = Math.max(width, 320);
    if (narrow) {
      const rowH = 46;
      const H = ORDER.length * rowH + 24;
      const core = { x: W - 56, y: H / 2 };
      const src = ORDER.map((k, i) => ({ k, x: 18, y: 24 + i * rowH + 10, dotX: W * 0.52 }));
      return { W, H, core, src, out: [] as { x: number; y: number }[] };
    }
    const H = 232;
    const core = { x: W * 0.5, y: H / 2 };
    const src = ORDER.map((k, i) => ({ k, x: 4, y: 30 + i * 43, dotX: Math.min(220, W * 0.22) }));
    const outX = W - Math.min(300, W * 0.3);
    const out = outputs.slice(0, 5).map((_, i, a) => ({ x: outX, y: H / 2 + (i - (a.length - 1) / 2) * 43 }));
    return { W, H, core, src, out };
  }, [width, narrow, outputs]);

  const inPaths = L.src.map((s) => {
    const mx = (s.dotX + L.core.x) / 2;
    return `M${s.dotX},${s.y} C${mx},${s.y} ${mx},${L.core.y} ${L.core.x - 30},${L.core.y}`;
  });
  const outPaths = L.out.map((o) => {
    const mx = (L.core.x + o.x) / 2;
    return `M${L.core.x + 30},${L.core.y} C${mx},${L.core.y} ${mx},${o.y} ${o.x - 8},${o.y}`;
  });

  // sparks along wires
  const spark = (pathEl: SVGPathElement | null, cls: string, r: number, delay: number, dur: number) => {
    const g = svg.current;
    if (!pathEl || !g) return;
    const len = pathEl.getTotalLength();
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("r", String(r));
    c.setAttribute("class", `spark ${cls}`);
    c.setAttribute("opacity", "0");
    g.appendChild(c);
    const o = { t: 0 };
    gsap.to(o, {
      t: 1,
      delay,
      duration: dur,
      ease: "power1.inOut",
      onStart: () => c.setAttribute("opacity", "1"),
      onUpdate: () => {
        const p = pathEl.getPointAtLength(o.t * len);
        c.setAttribute("cx", String(p.x));
        c.setAttribute("cy", String(p.y));
        c.setAttribute("opacity", String(o.t > 0.85 ? (1 - o.t) / 0.15 : 1));
      },
      onComplete: () => c.remove(),
    });
  };

  const fire = (opts: { inbound?: boolean; outbound?: boolean; changed?: string[] }) => {
    const g = svg.current;
    if (!g || prefersReducedMotion()) return;
    const ins = g.querySelectorAll<SVGPathElement>("path.wire.in");
    const outs = g.querySelectorAll<SVGPathElement>("path.wire.out");
    if (opts.inbound)
      ins.forEach((p, i) => {
        if (!p.classList.contains("bad")) spark(p, "", 2.5, i * 0.08, 0.9);
      });
    if (opts.changed?.length) {
      ins.forEach((p, i) => {
        if (opts.changed!.includes(ORDER[i])) {
          spark(p, "", 4, 0, 0.8);
          spark(p, "", 3, 0.18, 0.8);
        }
      });
      const halo = g.querySelector(".core-halo");
      if (halo) gsap.fromTo(halo, { attr: { r: 30 }, opacity: 0.9 }, { attr: { r: 64 }, opacity: 0, duration: 1.2, ease: "expo.out", delay: 0.7 });
    }
    if (opts.outbound) outs.forEach((p, i) => spark(p, "out", 2.5, 0.15 + i * 0.07, 0.8));
  };

  // first paint: one full pass so the wiring reads as connected
  const firstRun = useRef(true);
  useEffect(() => {
    if (!width || !firstRun.current) return;
    firstRun.current = false;
    const t = setTimeout(() => {
      fire({ inbound: true });
      setTimeout(() => fire({ outbound: true }), 900);
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width]);

  const wasFetching = useRef(false);
  useEffect(() => {
    if (live.fetching && !wasFetching.current) fire({ inbound: true });
    if (!live.fetching && wasFetching.current) fire({ outbound: true });
    wasFetching.current = live.fetching;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.fetching]);

  useEffect(() => {
    if (live.pulses > 0) fire({ changed: live.changedSources, outbound: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.pulses]);

  return (
    <div className="flow" ref={wrap} data-reveal>
      {width > 0 && (
        <svg ref={svg} viewBox={`0 0 ${L.W} ${L.H}`} width={L.W} height={L.H} role="img" aria-label="Live data flow from the five Google Sheets into the dashboard">
          {L.src.map((s, i) => {
            const st = sources?.[s.k];
            const bad = !!st && !st.ok && !st.stale;
            return (
              <g key={s.k}>
                <path className={`wire in ${st ? (bad ? "bad" : "ok") : ""}`} d={inPaths[i]} />
                <text className="node-label" x={s.x + 14} y={s.y - 3}>
                  {LABEL[s.k]}
                </text>
                <text className={`node-sub${bad ? " bad" : ""}`} x={s.x + 14} y={s.y + 12}>
                  {!st ? "connecting…" : bad ? "not reachable" : st.stale ? `delayed · ${ago(st.synced_at, now)}` : `read ${ago(st.synced_at, now)}`}
                </text>
                <circle className={`node-dot${bad ? " bad" : ""}`} cx={s.dotX} cy={s.y} r={4} />
              </g>
            );
          })}
          {L.out.map((o, i) => (
            <g key={outputs[i].label}>
              <path className="wire out ok" d={outPaths[i]} />
              <circle cx={o.x - 4} cy={o.y} r={3} fill={outputs[i].hot ? "var(--neg)" : "var(--series-ref)"} />
            </g>
          ))}
          <circle className="core-halo" cx={L.core.x} cy={L.core.y} r={30} />
          <circle className="core-ring" cx={L.core.x} cy={L.core.y} r={30} />
          <foreignObject x={L.core.x - 22} y={L.core.y - 9} width={44} height={18}>
            <div style={{ width: 44, height: 18, background: "var(--brand)", WebkitMaskImage: "url(/brand/flo-letters-navy.png)", maskImage: "url(/brand/flo-letters-navy.png)", WebkitMaskSize: "contain", maskSize: "contain", WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", WebkitMaskPosition: "center", maskPosition: "center" }} />
          </foreignObject>
        </svg>
      )}
      {!narrow &&
        L.out.map((o, i) => (
          <Link
            key={outputs[i].label}
            to={outputs[i].to}
            style={{ position: "absolute", left: `${(o.x / L.W) * 100}%`, top: o.y - 17, paddingLeft: 10, textDecoration: "none", lineHeight: 1.2, maxWidth: 290 }}
          >
            <span style={{ display: "block", fontSize: 12, color: "var(--muted)" }}>{outputs[i].label}</span>
            <span style={{ display: "block", fontSize: 14, fontWeight: 600, color: outputs[i].hot ? "var(--neg)" : "var(--ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{outputs[i].value}</span>
          </Link>
        ))}
    </div>
  );
}
