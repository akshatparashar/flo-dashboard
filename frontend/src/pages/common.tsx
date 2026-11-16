import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef, type ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import type { Envelope } from "../api/types";
import { prefersReducedMotion } from "../components/charts/common";
import { ErrorState, PageSkeleton } from "../components/ui";
import { clockIST } from "../lib/format";

export function PageHead({ title, lede, meta }: { title: string; lede?: ReactNode; meta?: Envelope["meta"] }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {meta && (
        <div className="stamp" title="Time the Google Sheets were last read (India time)">
          {meta.fy} · sheets read at {clockIST(meta.synced_at)}
          {meta.source === "demo" && <span className="demo"> · demo data</span>}
        </div>
      )}
    </div>
  );
}

/** Loading, error and refetch states for a page, plus the one entrance: blocks rise in once when a page first
 *  has data. Filter changes keep the old numbers on screen (dimmed) until the new ones arrive. */
export function PageState<T extends Envelope>({ q, children }: { q: UseQueryResult<T, Error>; children: (data: T) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const has = !!q.data;
  useGSAP(
    () => {
      if (!has || !ref.current || prefersReducedMotion()) return;
      gsap.fromTo(ref.current.querySelectorAll("[data-reveal]"), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.55, ease: "power3.out", stagger: 0.035, clearProps: "transform,opacity" });
    },
    { scope: ref, dependencies: [has] },
  );
  if (!q.data && q.isPending) return <PageSkeleton />;
  if (!q.data && q.error) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  return (
    <div ref={ref} className={q.isPlaceholderData ? "updating" : undefined} aria-busy={q.isFetching}>
      {children(q.data)}
    </div>
  );
}
