import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useMemo, useRef, useState } from "react";
import type { SeriesChart } from "../../api/types";
import { fmtInt, inr, shortMonth, titleCase } from "../../lib/format";
import { ChartFrame, colorFor, labelStep, niceScale, prefersReducedMotion, tickText, Tooltip, useWidth, type TipState } from "./common";

interface Props {
  data: SeriesChart;
  height?: number;
  stacked?: boolean;
  money?: boolean;          // values in rupees
  unit?: string;            // "pcs", "mtr"
  label: string;
  months?: boolean;         // categories are month labels
  names?: boolean;          // categories are entity names (title-cased)
  colors?: Record<string, string>;
  reference?: { value: number; label: string };   // 1px dashed line, label at its end
}

/** Vertical columns, grouped or stacked. Square bases, 2px top radius, 1px seams between stacked segments. */
export function Bars({ data, height = 260, stacked = false, money = false, unit = "", label, months = false, names = false, colors, reference }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const series = data.series.filter((s) => s.values.some((v) => v !== 0));
  const cats = data.categories;
  const color = (n: string, i: number) => colors?.[n] ?? colorFor(n, i);

  const m = { t: 10, r: 4, b: 26, l: 44 };
  const iw = Math.max(0, width - m.l - m.r);
  const ih = height - m.t - m.b;

  const { y, ticks, band } = useMemo(() => {
    const max = stacked
      ? Math.max(0, ...cats.map((_, i) => series.reduce((a, s) => a + Math.max(0, s.values[i] ?? 0), 0)))
      : Math.max(0, ...series.flatMap((s) => s.values));
    const { s, ticks } = niceScale(0, Math.max(max, reference?.value ?? 0), [ih, 0], 4);
    return { y: s, ticks, band: cats.length ? iw / cats.length : 0 };
  }, [cats, series, stacked, ih, iw, reference?.value]);

  const groupW = Math.min(band * 0.68, stacked ? 44 : 22 * Math.max(1, series.length) + 8);
  const barW = stacked ? groupW : Math.max(2, (groupW - (series.length - 1) * 2) / Math.max(1, series.length));
  const step = labelStep(cats.length, iw, months ? 46 : 70);
  const fmtV = (v: number) => (money ? inr(v) : `${fmtInt(v)}${unit ? ` ${unit}` : ""}`);
  const catLabel = (c: string) => (months ? shortMonth(c) : names ? titleCase(c) : c);

  useGSAP(
    () => {
      if (!svgRef.current || prefersReducedMotion()) return;
      gsap.fromTo(
        svgRef.current.querySelectorAll("rect.bar"),
        { scaleY: 0, transformOrigin: "50% 100%" },
        { scaleY: 1, duration: 0.7, ease: "expo.out", stagger: { each: 0.012, from: "start" } },
      );
    },
    { scope: svgRef, dependencies: [JSON.stringify(data), width > 0], revertOnUpdate: true },
  );

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <ChartFrame height={height} label={label}>
        {width > 0 && (
          <svg ref={svgRef} width={width} height={height} onMouseLeave={() => setTip(null)}>
            <g className="grid" transform={`translate(${m.l},${m.t})`}>
              {ticks.map((t) => (
                <g key={t} transform={`translate(0,${y(t)})`}>
                  {t !== 0 && <line x1={0} x2={iw} />}
                  <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                    {tickText(t, money)}
                  </text>
                </g>
              ))}
            </g>
            <g transform={`translate(${m.l},${m.t})`}>
              {cats.map((c, i) => {
                const x0 = i * band + (band - groupW) / 2;
                let acc = 0;
                return (
                  <g
                    key={c}
                    onMouseMove={(e) => {
                      const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                      setTip({
                        x: e.clientX - r.left,
                        y: e.clientY - r.top,
                        title: catLabel(c),
                        rows: series.map((s, k) => ({ name: s.name, color: color(s.name, k), value: fmtV(s.values[i] ?? 0) })),
                      });
                    }}
                  >
                    <rect className="hover-band" x={i * band} y={0} width={band} height={ih} opacity={tip?.title === catLabel(c) ? 1 : 0} />
                    {series.map((s, k) => {
                      const v = Math.max(0, s.values[i] ?? 0);
                      if (stacked) {
                        const top = y(acc + v);
                        const h = y(acc) - top;
                        acc += v;
                        return h > 0 ? (
                          <rect key={s.name} className="bar" x={x0} y={top} width={barW} height={Math.max(0, h - (k < series.length - 1 ? 1 : 0))} fill={color(s.name, k)} rx={k === series.length - 1 ? 2 : 0} />
                        ) : null;
                      }
                      const h = ih - y(v);
                      return h > 0 ? <rect key={s.name} className="bar" x={x0 + k * (barW + 2)} y={y(v)} width={barW} height={h} fill={color(s.name, k)} rx={2} /> : null;
                    })}
                    {i % step === 0 && (
                      <text className="xtick" x={i * band + band / 2} y={ih + 18} textAnchor="middle">
                        {catLabel(c).length > 12 ? `${catLabel(c).slice(0, 11)}…` : catLabel(c)}
                      </text>
                    )}
                  </g>
                );
              })}
              <line className="baseline" x1={0} x2={iw} y1={ih} y2={ih} />
              {reference && reference.value > 0 && (
                <g pointerEvents="none">
                  <line x1={0} x2={iw} y1={y(reference.value)} y2={y(reference.value)} stroke="var(--series-ref)" strokeDasharray="5 4" strokeWidth={1.25} />
                  <text className="tick" x={iw} y={y(reference.value) - 6} textAnchor="end" style={{ fill: "var(--ink-2)", fontWeight: 560 }}>
                    {reference.label}
                  </text>
                </g>
              )}
            </g>
          </svg>
        )}
      </ChartFrame>
      <Tooltip tip={tip} />
    </div>
  );
}
