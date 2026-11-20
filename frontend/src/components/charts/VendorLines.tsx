import { useMemo, useState } from "react";
import { inr } from "../../lib/format";
import { niceScale, tickText, useWidth } from "./common";

interface Props {
  categories: string[];
  series: { name: string; values: (number | null)[]; best: boolean[] }[];
  colors: string[];
  label: string;
}

/** One line per vendor across the fabric categories: where a line sits lowest is the cheapest vendor for that fabric
 *  (★ marks the best price). A vendor that does not quote a fabric simply has no point there. Hover a vendor in the
 *  key, or a point, to follow one line. */
export function VendorLines({ categories, series, colors, label }: Props) {
  const [ref, avail] = useWidth<HTMLDivElement>();
  const [focus, setFocus] = useState<string | null>(null);
  const height = 380;
  const m = { t: 22, r: 24, b: 64, l: 56 };
  const n = categories.length;
  const width = Math.max(avail, m.l + m.r + n * 78);
  const iw = width - m.l - m.r;
  const ih = height - m.t - m.b;
  const step = n > 1 ? iw / n : iw;
  const px = (i: number) => i * step + step / 2;
  const max = Math.max(0, ...series.flatMap((s) => s.values.map((v) => v ?? 0)));
  const { s: y, ticks } = useMemo(() => niceScale(0, max, [ih, 0], 5), [max, ih]);
  if (!n || !max) return <div className="state">No rates for these filters.</div>;
  const color = (k: number) => colors[k % colors.length];
  return (
    <div ref={ref}>
      <div className="vd-key" role="group" aria-label="Vendors">
        {series.map((s, k) => (
          <button key={s.name} type="button" className={focus && focus !== s.name ? "dim" : undefined} onMouseEnter={() => setFocus(s.name)} onMouseLeave={() => setFocus(null)} onFocus={() => setFocus(s.name)} onBlur={() => setFocus(null)}>
            <i style={{ background: color(k) }} />
            {s.name}
          </button>
        ))}
      </div>
      <div className="ff-scroll">
        <div className="chart" role="img" aria-label={label} style={{ height, width }}>
          {avail > 0 && (
            <svg width={width} height={height}>
              <g transform={`translate(${m.l},${m.t})`}>
                <g className="grid">
                  {ticks.map((t) => (
                    <g key={t} transform={`translate(0,${y(t)})`}>
                      <line x1={0} x2={iw} />
                      <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                        {tickText(t, true)}
                      </text>
                    </g>
                  ))}
                </g>
                {categories.map((c, i) => (
                  <text key={c} className="ff-x" x={px(i)} y={ih + 22} textAnchor="middle">
                    {c.length > 14 ? `${c.slice(0, 13)}…` : c}
                  </text>
                ))}
                {series.map((s, k) => {
                  const pts = s.values.map((v, i) => (v === null ? null : [px(i), y(v), v, i] as const)).filter((p): p is readonly [number, number, number, number] => p !== null);
                  const faded = focus !== null && focus !== s.name;
                  return (
                    <g key={s.name} opacity={faded ? 0.12 : 1} className="vl-series" onMouseEnter={() => setFocus(s.name)} onMouseLeave={() => setFocus(null)}>
                      {pts.length > 1 && <polyline points={pts.map((p) => `${p[0]},${p[1]}`).join(" ")} fill="none" stroke={color(k)} strokeWidth={focus === s.name ? 3.4 : 2.2} strokeLinejoin="round" strokeLinecap="round" />}
                      {pts.map(([cx, cy, v, i]) => (
                        <g key={i}>
                          <title>{`${s.name} · ${categories[i]}: ${inr(v)}${s.best[i] ? " ★ Best Price" : ""}`}</title>
                          {s.best[i] && <circle cx={cx} cy={cy} r={10} fill="none" stroke="var(--pos)" strokeWidth={2} />}
                          <circle cx={cx} cy={cy} r={s.best[i] ? 5.5 : 4.5} fill={color(k)} stroke="var(--sheet)" strokeWidth={2} />
                          {s.best[i] && (
                            <text className="vl-star" x={cx} y={cy - 16} textAnchor="middle">
                              ★ {inr(v)}
                            </text>
                          )}
                        </g>
                      ))}
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </div>
      </div>
    </div>
  );
}
