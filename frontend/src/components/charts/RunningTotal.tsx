import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { area as d3area, line as d3line } from "d3-shape";
import { useId, useMemo, useRef, useState } from "react";
import { inr, inrShort, shortMonth } from "../../lib/format";
import { labelStep, niceScale, prefersReducedMotion, tickText, Tooltip, useWidth, type TipState } from "./common";

interface Props {
  categories: string[];
  thisYear: { name: string; values: number[] };
  lastYear: { name: string; values: number[] };
  label: string;
  height?: number;
}

const THIS = "var(--accent)";
const LAST = "var(--series-ref)";

/** A number that counts up to its value when it first appears (plain text when motion is reduced). */
function CountUp({ value, format }: { value: number; format: (v: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useGSAP(
    () => {
      const el = ref.current;
      if (!el) return;
      if (prefersReducedMotion()) {
        el.textContent = format(value);
        return;
      }
      const o = { v: 0 };
      gsap.to(o, { v: value, duration: 1.3, ease: "power2.out", onUpdate: () => (el.textContent = format(o.v)) });
    },
    { dependencies: [value], revertOnUpdate: true },
  );
  return <span ref={ref}>{format(value)}</span>;
}

/** Running total of two years against each other: the year so far as a glowing area line that draws itself in,
 *  last year dashed behind it, the gap between them shaded, month dots that pop in, end-of-line value tags,
 *  a hover crosshair that reads out both years and how far ahead (or behind) this year is, and three headline
 *  figures that count up. */
export function RunningTotal({ categories, thisYear, lastYear, label, height = 320 }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [hover, setHover] = useState<number | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);

  const n = categories.length;
  const m = { t: 18, r: 18, b: 28, l: 52 };
  const iw = Math.max(0, width - m.l - m.r);
  const ih = height - m.t - m.b;
  const xAt = (i: number) => (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  const a = thisYear.values;
  const b = lastYear.values;
  const max = Math.max(0, ...a, ...b);
  const { s: y, ticks } = useMemo(() => niceScale(0, max, [ih, 0], 4), [max, ih]);

  const lastIdx = n - 1;
  const endA = a[lastIdx] ?? 0;
  const endB = b[lastIdx] ?? 0;
  const gap = endA - endB;
  const gapPct = endB ? (gap / endB) * 100 : null;
  const ahead = gap >= 0;

  const pts = categories.map((_, i) => ({ x: xAt(i), a: a[i] ?? 0, b: b[i] ?? 0 }));
  const lineA = d3line<(typeof pts)[number]>().x((d) => d.x).y((d) => y(d.a))(pts) ?? "";
  const lineB = d3line<(typeof pts)[number]>().x((d) => d.x).y((d) => y(d.b))(pts) ?? "";
  const areaA = d3area<(typeof pts)[number]>().x((d) => d.x).y0(y(0)).y1((d) => y(d.a))(pts) ?? "";
  const band = d3area<(typeof pts)[number]>().x((d) => d.x).y0((d) => y(d.b)).y1((d) => y(d.a))(pts) ?? "";
  const step = labelStep(n, iw, 50);

  useGSAP(
    () => {
      const svg = svgRef.current;
      if (!svg || prefersReducedMotion() || !iw) return;
      const tl = gsap.timeline();
      tl.fromTo(svg.querySelector(`#rt-clip-${uid} rect`), { attr: { width: 0 } }, { attr: { width: iw + 4 }, duration: 1.5, ease: "power2.inOut" }, 0);
      svg.querySelectorAll<SVGPathElement>("path.rt-line").forEach((p) => {
        const len = p.getTotalLength();
        tl.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.5, ease: "power2.inOut", clearProps: "strokeDasharray,strokeDashoffset" }, 0);
      });
      tl.fromTo(svg.querySelectorAll(".rt-dot"), { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.45, ease: "back.out(2.4)", stagger: 0.09 }, 0.35);
      tl.fromTo(svg.querySelectorAll(".rt-tag"), { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.5, ease: "power2.out", stagger: 0.12 }, 1.3);
      tl.fromTo(svg.querySelectorAll(".rt-pulse"), { scale: 1, opacity: 0.5, transformOrigin: "50% 50%" }, { scale: 3.2, opacity: 0, duration: 1.6, ease: "power1.out", repeat: 2, repeatDelay: 0.3 }, 1.5);
    },
    { scope: svgRef, dependencies: [JSON.stringify([a, b]), width > 0], revertOnUpdate: true },
  );

  if (!n) return <div className="state">No months to show.</div>;
  const tagY = (v: number, other: number) => (v >= other ? y(v) - 30 : y(v) + 12);

  return (
    <div ref={ref} className="rt">
      <div className="rt-stats">
        <div>
          <span className="rt-k">
            <i style={{ background: THIS }} />
            {thisYear.name}
          </span>
          <b className="num">
            <CountUp value={endA} format={inrShort} />
          </b>
        </div>
        <div>
          <span className="rt-k">
            <i className="dash" style={{ borderColor: LAST }} />
            {lastYear.name} (same months)
          </span>
          <b className="num">
            <CountUp value={endB} format={inrShort} />
          </b>
        </div>
        <div className={ahead ? "up" : "down"}>
          <span className="rt-k">{ahead ? "Ahead by" : "Behind by"}</span>
          <b className="num">
            <CountUp value={Math.abs(gap)} format={inrShort} />
            {gapPct !== null && (
              <em>
                {ahead ? "▲" : "▼"} {Math.abs(gapPct).toFixed(1)}%
              </em>
            )}
          </b>
        </div>
      </div>

      <div className="chart" role="img" aria-label={label} style={{ height, position: "relative" }}>
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
              const d = (a[i] ?? 0) - (b[i] ?? 0);
              setTip({
                x: m.l + xAt(i),
                y: Math.min(e.clientY - r.top, height - 40),
                title: shortMonth(categories[i]),
                rows: [
                  { name: thisYear.name, color: THIS, value: inr(a[i] ?? 0) },
                  { name: lastYear.name, color: LAST, value: inr(b[i] ?? 0) },
                  { name: d >= 0 ? "Ahead by" : "Behind by", color: d >= 0 ? "var(--pos)" : "var(--neg)", value: inr(Math.abs(d)) },
                ],
              });
            }}
            onMouseLeave={() => {
              setHover(null);
              setTip(null);
            }}
          >
            <defs>
              <linearGradient id={`rt-fill-${uid}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={THIS} stopOpacity={0.38} />
                <stop offset="100%" stopColor={THIS} stopOpacity={0} />
              </linearGradient>
              <clipPath id={`rt-clip-${uid}`}>
                <rect x={-2} y={-12} width={iw + 4} height={ih + 24} />
              </clipPath>
            </defs>
            <g className="grid" transform={`translate(${m.l},${m.t})`}>
              {ticks.map((t) => (
                <g key={t} transform={`translate(0,${y(t)})`}>
                  {t !== 0 && <line x1={0} x2={iw} />}
                  <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                    {tickText(t, true)}
                  </text>
                </g>
              ))}
            </g>
            <g transform={`translate(${m.l},${m.t})`}>
              <line className="baseline" x1={0} x2={iw} y1={y(0)} y2={y(0)} />
              <g clipPath={`url(#rt-clip-${uid})`}>
                <path d={band} fill={THIS} fillOpacity={0.09} />
                <path d={areaA} fill={`url(#rt-fill-${uid})`} />
                <path className="rt-line" d={lineB} fill="none" stroke={LAST} strokeWidth={1.75} strokeLinejoin="round" strokeDasharray="6 5" opacity={0.85} />
                <path className="rt-line" d={lineA} fill="none" stroke={THIS} strokeWidth={2.75} strokeLinejoin="round" strokeLinecap="round" />
              </g>
              {hover !== null && <line x1={xAt(hover)} x2={xAt(hover)} y1={0} y2={ih} stroke="var(--faint)" strokeDasharray="3 3" />}
              {pts.map((p, i) => (
                <g key={categories[i]}>
                  <circle className="rt-dot" cx={p.x} cy={y(p.b)} r={hover === i ? 4 : 2.75} fill="var(--sheet)" stroke={LAST} strokeWidth={1.5} />
                  <circle className="rt-dot" cx={p.x} cy={y(p.a)} r={hover === i ? 5.5 : 3.75} fill="var(--sheet)" stroke={THIS} strokeWidth={2.25} />
                </g>
              ))}
              {/* the live end of the line pulses a few times, then rests */}
              <circle className="rt-pulse" cx={xAt(lastIdx)} cy={y(endA)} r={5} fill={THIS} />
              {[
                { v: endA, other: endB, c: THIS, k: "a" },
                { v: endB, other: endA, c: LAST, k: "b" },
              ].map(({ v, other, c, k }) => {
                const text = inrShort(v);
                const w = text.length * 7 + 16;
                const x = Math.min(Math.max(xAt(lastIdx) - w / 2, 0), Math.max(0, iw - w));
                return (
                  <g key={k} className="rt-tag" transform={`translate(${x},${tagY(v, other)})`}>
                    <rect width={w} height={20} rx={10} fill={c} />
                    <text x={w / 2} y={14} textAnchor="middle" className="rt-tag-text">
                      {text}
                    </text>
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
        <Tooltip tip={tip} />
      </div>
    </div>
  );
}
