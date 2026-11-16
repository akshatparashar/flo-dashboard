import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { line as d3line, area as d3area } from "d3-shape";
import { useMemo, useRef, useState } from "react";
import { fmtInt, inr, shortMonth } from "../../lib/format";
import { colorFor, labelStep, niceScale, prefersReducedMotion, tickText, Tooltip, useWidth, type TipState } from "./common";

export interface LineSeries {
  name: string;
  values: (number | null)[];
  dashed?: boolean;
  fill?: boolean;
  axis?: "left" | "right";
  unit?: string;
  color?: string;
}

interface Props {
  categories: string[];
  series: LineSeries[];
  height?: number;
  money?: boolean;
  label: string;
  rightUnit?: string;
  leftUnit?: string;
}

/** Straight-segment lines (never smoothed), optional flat 12% fill under one series, optional right axis. */
export function Lines({ categories: allCats, series: allSeries, height = 260, money = false, label, leftUnit = "", rightUnit = "" }: Props) {
  // a time line has no "(NO DATE)" point, and months that have not happened yet (all zero at the end) are not drawn
  const { categories, series } = useMemo(() => {
    const keep = allCats.map((c) => !c.startsWith("("));
    let last = allCats.length - 1;
    while (last > 0 && allSeries.every((s) => !s.values[last])) last--;
    const idx = allCats.map((_, i) => i).filter((i) => keep[i] && i <= Math.max(last, 1));
    return { categories: idx.map((i) => allCats[i]), series: allSeries.map((s) => ({ ...s, values: idx.map((i) => s.values[i]) })) };
  }, [allCats, allSeries]);
  const [ref, width] = useWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const hasRight = series.some((s) => s.axis === "right");
  const m = { t: 12, r: hasRight ? 46 : 8, b: 26, l: 46 };
  const iw = Math.max(0, width - m.l - m.r);
  const ih = height - m.t - m.b;
  const n = categories.length;
  const xAt = (i: number) => (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);

  const scales = useMemo(() => {
    const vals = (side: "left" | "right") =>
      series.filter((s) => (s.axis ?? "left") === side).flatMap((s) => s.values.filter((v): v is number => v !== null));
    const l = niceScale(Math.min(0, ...vals("left")), Math.max(0, ...vals("left")), [ih, 0], 4);
    const r = niceScale(0, Math.max(0, ...vals("right")), [ih, 0], 4);
    return { l, r };
  }, [series, ih]);

  const step = labelStep(n, iw, 50);
  const fmtV = (v: number | null, s: LineSeries) => (v === null ? "—" : money && (s.axis ?? "left") === "left" ? inr(v) : `${fmtInt(v)}${s.unit ? ` ${s.unit}` : ""}`);

  useGSAP(
    () => {
      if (!svgRef.current || prefersReducedMotion()) return;
      svgRef.current.querySelectorAll<SVGPathElement>("path.ln").forEach((p) => {
        const len = p.getTotalLength();
        if (p.classList.contains("dashed")) {
          gsap.fromTo(p, { opacity: 0 }, { opacity: 1, duration: 0.6 });
          return;
        }
        gsap.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.1, ease: "power2.out", clearProps: "strokeDasharray,strokeDashoffset" });
      });
      gsap.fromTo(svgRef.current.querySelectorAll("path.area"), { opacity: 0 }, { opacity: 1, duration: 0.9, delay: 0.3 });
    },
    { scope: svgRef, dependencies: [JSON.stringify(series), width > 0], revertOnUpdate: true },
  );

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div className="chart" role="img" aria-label={label} style={{ height }}>
        {width > 0 && (
          <svg
            ref={svgRef}
            width={width}
            height={height}
            onMouseMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const px = e.clientX - r.left - m.l;
              const i = Math.max(0, Math.min(n - 1, Math.round((px / Math.max(1, iw)) * (n - 1))));
              setHover(i);
              setTip({
                x: m.l + xAt(i),
                y: e.clientY - r.top,
                title: shortMonth(categories[i]),
                rows: series.map((s, k) => ({ name: s.name, color: s.color ?? colorFor(s.name, k), value: fmtV(s.values[i], s) })),
              });
            }}
            onMouseLeave={() => {
              setHover(null);
              setTip(null);
            }}
          >
            <g className="grid" transform={`translate(${m.l},${m.t})`}>
              {scales.l.ticks.map((t) => (
                <g key={t} transform={`translate(0,${scales.l.s(t)})`}>
                  {t !== 0 && <line x1={0} x2={iw} />}
                  <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                    {tickText(t, money)}
                    {leftUnit && t === scales.l.ticks[scales.l.ticks.length - 1] ? ` ${leftUnit}` : ""}
                  </text>
                </g>
              ))}
              {hasRight &&
                scales.r.ticks.map((t) => (
                  <text key={t} className="tick" x={iw + 8} y={scales.r.s(t)} dy="0.32em">
                    {tickText(t, false)}
                    {rightUnit && t === scales.r.ticks[scales.r.ticks.length - 1] ? ` ${rightUnit}` : ""}
                  </text>
                ))}
            </g>
            <g transform={`translate(${m.l},${m.t})`}>
              <line className="baseline" x1={0} x2={iw} y1={scales.l.s(0)} y2={scales.l.s(0)} />
              {hover !== null && <line x1={xAt(hover)} x2={xAt(hover)} y1={0} y2={ih} stroke="var(--faint)" strokeDasharray="3 3" />}
              {series.map((s, k) => {
                const sc = (s.axis ?? "left") === "right" ? scales.r.s : scales.l.s;
                const pts = s.values.map((v, i) => [xAt(i), v] as const);
                const ln = d3line<(typeof pts)[number]>()
                  .defined((d) => d[1] !== null)
                  .x((d) => d[0])
                  .y((d) => sc(d[1] as number));
                const c = s.color ?? colorFor(s.name, k);
                const ar = d3area<(typeof pts)[number]>()
                  .defined((d) => d[1] !== null)
                  .x((d) => d[0])
                  .y0(sc(0))
                  .y1((d) => sc(d[1] as number));
                return (
                  <g key={s.name}>
                    {s.fill && <path className="area" d={ar(pts) ?? ""} fill={c} fillOpacity={0.12} />}
                    <path className={`ln${s.dashed ? " dashed" : ""}`} d={ln(pts) ?? ""} fill="none" stroke={c} strokeWidth={s.dashed ? 1.5 : 2.25} strokeDasharray={s.dashed ? "5 4" : undefined} strokeLinejoin="round" />
                    {hover !== null && s.values[hover] !== null && <circle cx={xAt(hover)} cy={sc(s.values[hover] as number)} r={4} fill="var(--sheet)" stroke={c} strokeWidth={2} />}
                  </g>
                );
              })}
              {categories.map((c, i) =>
                i % step === 0 ? (
                  <text key={c} className="xtick" x={xAt(i)} y={ih + 18} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}>
                    {shortMonth(c)}
                  </text>
                ) : null,
              )}
            </g>
          </svg>
        )}
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}
