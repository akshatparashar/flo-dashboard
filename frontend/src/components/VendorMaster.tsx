import { Download } from "lucide-react";
import { downloadCsv } from "../lib/csv";
import { inr } from "../lib/format";

interface Props {
  categories: string[];
  series: { name: string; values: (number | null)[]; best: boolean[] }[];
  name: string;
}

/** Master price table: fabric (design) category down the side, vendors across, each vendor's cheapest rate in the
 *  cell. Cheap cells are green, dear ones red (scaled within the row); the best price is bold with a ★. */
export function VendorMaster({ categories, series, name }: Props) {
  if (!categories.length) return <div className="state">No rates for these filters.</div>;
  const csv = ["Fabric", ...series.map((s) => s.name)].join(",") + "\r\n" + categories.map((c, i) => [c, ...series.map((s) => s.values[i] ?? "")].join(",")).join("\r\n");
  return (
    <>
      <div className="vm-wrap">
        <table className="vm-table">
          <thead>
            <tr>
              <th className="l">Fabric</th>
              {series.map((s) => (
                <th key={s.name}>{s.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {categories.map((c, i) => {
              const vals = series.map((s) => s.values[i]).filter((v): v is number => v !== null);
              const lo = Math.min(...vals);
              const hi = Math.max(...vals);
              return (
                <tr key={c}>
                  <th className="l" scope="row">
                    {c}
                  </th>
                  {series.map((s) => {
                    const v = s.values[i];
                    if (v === null) return <td key={s.name} className="none">·</td>;
                    const t = hi > lo ? (v - lo) / (hi - lo) : 0;
                    const tint = t < 0.5 ? `color-mix(in srgb, var(--pos) ${Math.round(26 - t * 40)}%, transparent)` : `color-mix(in srgb, var(--neg) ${Math.round((t - 0.5) * 44)}%, transparent)`;
                    return (
                      <td key={s.name} className={s.best[i] ? "best" : undefined} style={{ background: tint }} title={`${s.name} · ${c}: ${inr(v)}`}>
                        {s.best[i] ? "★ " : ""}
                        {inr(v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button type="button" className="btn ff-dl" onClick={() => downloadCsv(`${name}.csv`, csv)}>
        <Download aria-hidden="true" /> Download CSV
      </button>
    </>
  );
}
