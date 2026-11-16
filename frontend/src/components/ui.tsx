import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { AlertTriangle, CheckCircle2, Info, RefreshCw, XCircle } from "lucide-react";
import { useRef, type ReactNode } from "react";
import type { Kpi, Notice as NoticeT } from "../api/types";
import { fmtKpi, titleCase } from "../lib/format";
import { prefersReducedMotion } from "./charts/common";

export function Panel({ title, sub, right, children, foot, className = "", flush = false, id }: { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; foot?: ReactNode; className?: string; flush?: boolean; id?: string }) {
  return (
    <section className={`panel ${className}`} aria-labelledby={id ? `${id}-t` : undefined} data-reveal>
      {(title || right) && (
        <div className="panel-head">
          <div>
            {title && <h3 id={id ? `${id}-t` : undefined}>{title}</h3>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {right}
        </div>
      )}
      <div className={`panel-body${flush ? " flush" : ""}`}>{children}</div>
      {foot && <div className="panel-foot">{foot}</div>}
    </section>
  );
}

export function Section({ title, sub, right, children }: { title: string; sub?: ReactNode; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      <div className="section-title">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

/** A number that tweens from its previous value when live data changes it. */
function AnimatedValue({ kpi }: { kpi: Kpi }) {
  const ref = useRef<HTMLSpanElement>(null);
  const last = useRef<number | null>(null);
  const shown = fmtKpi(kpi.value, kpi.format);
  useGSAP(
    () => {
      const el = ref.current;
      const v = kpi.value;
      if (!el || typeof v !== "number") return;
      const from = last.current ?? 0;
      last.current = v;
      if (prefersReducedMotion() || from === v) {
        el.textContent = fmtKpi(v, kpi.format).value;
        return;
      }
      const o = { n: from };
      gsap.to(o, {
        n: v,
        duration: from === 0 ? 1.1 : 0.8,
        ease: "power3.out",
        onUpdate: () => {
          el.textContent = fmtKpi(o.n, kpi.format).value;
        },
        onComplete: () => {
          el.textContent = fmtKpi(v, kpi.format).value;
        },
      });
    },
    { dependencies: [kpi.value, kpi.format] },
  );
  return <span ref={ref}>{shown.value}</span>;
}

export function KpiStrip({ kpis, cols, lead }: { kpis: Kpi[]; cols?: number; lead?: string[] }) {
  const n = cols ?? Math.min(kpis.length, kpis.length % 4 === 0 || kpis.length > 6 ? 4 : kpis.length === 5 ? 5 : 3);
  return (
    <div className="kpis" style={{ ["--cols" as string]: n }} data-reveal>
      {kpis.map((k) => {
        const f = fmtKpi(k.value, k.format);
        const unit = f.unit || k.unit;
        const isText = k.format === "text";
        return (
          <div className={`kpi${k.tone === "alert" && typeof k.value === "number" && k.value > 0 ? " is-alert" : ""}${lead?.includes(k.id) ? " lead" : ""}`} key={k.id}>
            <div className="kpi-label" title={k.hint}>
              {k.label}
              {k.hint && k.hint.length > 38 && <Info aria-label={k.hint} />}
            </div>
            <div className={`kpi-value num${isText ? " is-text" : ""}`} title={typeof k.value === "string" ? k.value : undefined}>
              {isText ? (typeof k.value === "string" && /^[^a-z]*[A-Z][^a-z]*$/.test(k.value) ? titleCase(k.value) : k.value) : <AnimatedValue kpi={k} />}
              {unit && !isText && <span className="u">{unit}</span>}
            </div>
            {k.hint && k.hint.length <= 38 && <div className="kpi-hint">{k.hint}</div>}
          </div>
        );
      })}
    </div>
  );
}

const ICON = { info: Info, success: CheckCircle2, warning: AlertTriangle, error: XCircle };

export function Notice({ n }: { n: NoticeT }) {
  const Icon = ICON[n.kind] ?? Info;
  return (
    <div className={`notice ${n.kind}`} role={n.kind === "error" ? "alert" : undefined}>
      <Icon aria-hidden="true" />
      <span>{n.text}</span>
    </div>
  );
}

export function Notices({ items }: { items?: NoticeT[] }) {
  if (!items?.length) return null;
  return (
    <>
      {items.map((n, i) => (
        <Notice key={i} n={n} />
      ))}
    </>
  );
}

export function Skeleton({ h = 16, w = "100%", r = 8 }: { h?: number; w?: number | string; r?: number }) {
  return <div className="skel" style={{ height: h, width: w, borderRadius: r }} />;
}

export function PageSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <div style={{ display: "grid", gap: 10, marginBottom: 24 }}>
        <Skeleton h={34} w={280} />
        <Skeleton h={18} w={420} />
      </div>
      <Skeleton h={92} r={12} />
      <div className="grid" style={{ marginTop: 16 }}>
        <div className="span-7">
          <Skeleton h={320} r={12} />
        </div>
        <div className="span-5">
          <Skeleton h={320} r={12} />
        </div>
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state" role="alert">
      <XCircle width={28} height={28} color="var(--neg)" aria-hidden="true" />
      <h3>This view could not load</h3>
      <p style={{ maxWidth: 520 }}>{message}</p>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          <RefreshCw /> Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title = "Nothing here yet", children }: { title?: string; children?: ReactNode }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}
