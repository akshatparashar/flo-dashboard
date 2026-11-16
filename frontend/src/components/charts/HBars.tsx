import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useMemo, useRef, useState } from "react";
import type { SeriesChart } from "../../api/types";
import { fmtInt, inr, titleCase } from "../../lib/format";
import { colorFor, niceScale, prefersReducedMotion, tickText, Tooltip, useWidth, type TipState } from "./common";

interface Props {
  data: SeriesChart;
  money?: boolean;
  unit?: string;
  label: string;
  descending?: boolean;     // biggest first (input arrives smallest-first from the API)
  max?: number;             // cap rows
  sortBy?: string;          // sort by this series instead of the row total
}

/** Horizontal stacked bars, one row per entity: who ranks, and how each splits. */
export function HBars({ data, money = false, unit = "", label, descending = true, max = 14, sortBy }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const series = data.series.filter((s) => s.values.some((v) => v !== 0));
  const rows = useMemo(() => {
    const idx = data.categories.map((c, i) => ({ c, i, total: series.reduce((a, s) => a + Math.max(0, s.values[i] ?? 0), 0) }));
    const key = sortBy ? series.find((s) => s.name === sortBy) : undefined;
    const by = (r: (typeof idx)[number]) => (key ? key.values[r.i] ?? 0 : r.total);
    const ordered = descending ? [...idx].sort((a, b) => by(b) - by(a) || b.total - a.total) : idx;
    return ordered.slice(0, max);
  }, [data, series, descending, max, sortBy]);

  const rowH = 30;
  const nameW = Math.min(150, Math.max(90, width * 0.28));
  const m = { t: 4, r: 56, b: 22, l: nameW };
  const iw = Math.max(0, width - m.l - m.r);
  const height = m.t + m.b + rows.length * rowH;
  const maxV = Math.max(0, ...rows.map((r) => r.total));
  const { s: x, ticks } = niceScale(0, maxV, [0, iw], 4);
  const fmtV = (v: number) => (money ? inr(v) : `${fmtInt(v)}${unit ? ` ${unit}` : ""}`);

  useGSAP(
    () => {
      if (!svgRef.current || prefersReducedMotion()) return;
      gsap.fromTo(svgRef.current.querySelectorAll("rect.bar"), { scaleX: 0, transformOrigin: "0% 50%" }, { scaleX: 1, duration: 0.7, ease: "expo.out", stagger: 0.02 });
    },
    { scope: svgRef, dependencies: [JSON.stringify(data), width > 0], revertOnUpdate: true },
  );

  if (!rows.length) return <div className="state">Nothing to show for these filters.</div>;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div className="chart" role="img" aria-label={label} style={{ height }}>
        {width > 0 && (
          <svg ref={svgRef} width={width} height={height} onMouseLeave={() => setTip(null)}>
            <g className="grid" transform={`translate(${m.l},${m.t})`}>
              {ticks.map((t) => (
                <g key={t} transform={`translate(${x(t)},0)`}>
                  {t !== 0 && <line y1={0} y2={rows.length * rowH} />}
                  <text className="tick" y={rows.length * rowH + 15} textAnchor="middle">
                    {tickText(t, money)}
                  </text>
                </g>
              ))}
            </g>
            <g transform={`translate(0,${m.t})`}>
              {rows.map((r, j) => {
                let acc = 0;
                const name = titleCase(r.c);
                return (
                  <g
                    key={r.c}
                    transform={`translate(0,${j * rowH})`}
                    onMouseMove={(e) => {
                      const b = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                      setTip({ x: e.clientX - b.left, y: e.clientY - b.top, title: name, rows: series.map((s, k) => ({ name: s.name, color: colorFor(s.name, k), value: fmtV(s.values[r.i] ?? 0) })) });
                    }}
                  >
                    <rect className="hover-band" x={0} y={1} width={width} height={rowH - 2} rx={6} opacity={tip?.title === name ? 1 : 0} />
                    <text className="xtick" x={8} y={rowH / 2} dy="0.32em" style={{ fill: "var(--ink)" }}>
                      {name.length > 18 ? `${name.slice(0, 17)}…` : name}
                    </text>
                    {series.map((s, k) => {
                      const v = Math.max(0, s.values[r.i] ?? 0);
                      const x0 = x(acc);
                      acc += v;
                      const w = x(acc) - x0;
                      return w > 0 ? <rect key={s.name} className="bar" x={m.l + x0} y={8} width={Math.max(0, w - 1)} height={rowH - 16} rx={2} fill={colorFor(s.name, k)} /> : null;
                    })}
                    <text className="val" x={m.l + x(r.total) + 6} y={rowH / 2} dy="0.32em">
                      {money ? tickText(r.total, true) : fmtInt(r.total)}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}
