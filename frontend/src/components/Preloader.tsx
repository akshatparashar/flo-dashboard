import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useEffect, useRef, useState } from "react";
import type { StatusData } from "../api/types";
import { ART, BRACKET, Wordmark } from "./Brand";
import { prefersReducedMotion } from "./charts/common";
import { navCollapsed } from "./shell/Shell";

const SOURCE_ORDER = ["tracker", "sample_summary", "overview_fabricators", "fabric_po", "target_revenue", "flo_future", "vendor_rate", "in_out_sale", "daily_delegation"];
const SOURCE_NAMES: Record<string, string> = {
  tracker: "Master sheet",
  sample_summary: "Samples",
  overview_fabricators: "Fabricators",
  fabric_po: "Fabric PO",
  target_revenue: "Target",
  flo_future: "FLO Future",
  vendor_rate: "Vendor rates",
  in_out_sale: "In/Out sale",
  daily_delegation: "Delegation",
};
const MIN_MS = 1900; // long enough for the bracket and the wordmark to finish drawing
const MAX_MS = 3200; // never hold the page for slow sheets: the pages show their own loading states

type Pt = [number, number];

function logoBox(vw: number, vh: number) {
  const w = Math.min(520, vw * 0.74);
  const h = (w * ART.h) / ART.w;
  return { x: (vw - w) / 2, y: (vh - h) / 2 - 36, w, h, s: w / ART.w };
}

function sheetBox(vw: number, vh: number, full: boolean) {
  if (full) return { l: 14, t: 14, r: vw - 14, b: vh - 14 };
  if (vw <= 1024) return { l: -2, t: 52, r: vw + 2, b: vh + 2 };
  return { l: navCollapsed() ? 68 : 236, t: 52, r: vw - 8, b: vh - 8 };
}

function pathOf(p: Pt[]) {
  return `M${p[0][0]},${p[0][1]} L${p[1][0]},${p[1][1]} L${p[2][0]},${p[2][1]} L${p[3][0]},${p[3][1]} L${p[4][0]},${p[4][1]}`;
}

/** FLO's open bracket draws itself like a wire, the wordmark appears inside it, the five sheets light up as they
 *  really load, then the bracket stretches into the sheet frame of the app: the logo becomes the interface. */
/** exit "sheet" opens the bracket into the dashboard's sheet frame; "page" opens it to the edges of the screen
 *  (the landing page). */
export function Preloader({ status, onDone, exit = "sheet" }: { status: StatusData | undefined; onDone: () => void; exit?: "sheet" | "page" }) {
  const root = useRef<HTMLDivElement>(null);
  const path = useRef<SVGPathElement>(null);
  const mark = useRef<HTMLDivElement>(null);
  const [vw, setVw] = useState(window.innerWidth);
  const [vh, setVh] = useState(window.innerHeight);
  const [t0] = useState(Date.now());
  const [ready, setReady] = useState(false);
  const exiting = useRef(false);

  useEffect(() => {
    const on = () => {
      setVw(window.innerWidth);
      setVh(window.innerHeight);
    };
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);

  const box = logoBox(vw, vh);
  const start: Pt[] = BRACKET.map(([x, y]) => [box.x + x * box.s, box.y + y * box.s] as Pt);

  // intro: draw the bracket, then reveal the wordmark
  useGSAP(
    () => {
      const p = path.current;
      if (!p) return;
      if (prefersReducedMotion()) {
        gsap.set(mark.current, { opacity: 1 });
        return;
      }
      const len = p.getTotalLength();
      gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
      gsap
        .timeline()
        .to(p, { strokeDashoffset: 0, duration: 1.05, ease: "power2.inOut" })
        .fromTo(mark.current, { opacity: 0, clipPath: "inset(0 100% 0 0)" }, { opacity: 1, clipPath: "inset(0 0% 0 0)", duration: 0.75, ease: "power3.out" }, "-=0.35")
        .fromTo(".sources span", { opacity: 0, y: 6 }, { opacity: 1, y: 0, stagger: 0.06, duration: 0.4, ease: "power2.out" }, "-=0.3");
    },
    { scope: root },
  );

  useEffect(() => {
    const done = status !== undefined;
    const wait = Math.max(0, MIN_MS - (Date.now() - t0));
    const timer = setTimeout(() => setReady(true), done ? wait : MAX_MS - (Date.now() - t0));
    return () => clearTimeout(timer);
  }, [status, t0]);

  // exit: the bracket stretches into the app's sheet frame, everything else fades
  useEffect(() => {
    if (!ready || exiting.current) return;
    exiting.current = true;
    if (prefersReducedMotion()) {
      gsap.to(root.current, { opacity: 0, duration: 0.25, onComplete: onDone });
      return;
    }
    const sb = sheetBox(vw, vh, exit === "page");
    const end: Pt[] = [
      [sb.r, sb.t + Math.min(160, (sb.b - sb.t) * 0.25)],
      [sb.r, sb.t],
      [sb.l, sb.t],
      [sb.l, sb.b],
      [sb.l + Math.min(260, (sb.r - sb.l) * 0.3), sb.b],
    ];
    const cur = start.map((p) => [...p]) as Pt[];
    const prog = { k: 0 };
    const tl = gsap.timeline({ onComplete: onDone });
    tl.to([mark.current, ".sources"], { opacity: 0, y: -8, duration: 0.35, ease: "power2.in" })
      .to(
        prog,
        {
          k: 1,
          duration: 0.85,
          ease: "expo.inOut",
          onUpdate: () => {
            for (let i = 0; i < 5; i++) {
              cur[i][0] = start[i][0] + (end[i][0] - start[i][0]) * prog.k;
              cur[i][1] = start[i][1] + (end[i][1] - start[i][1]) * prog.k;
            }
            path.current?.setAttribute("d", pathOf(cur));
            path.current?.setAttribute("stroke-width", String(ART.stroke * box.s + (1 - ART.stroke * box.s) * prog.k));
          },
        },
        "-=0.1",
      )
      // fade the backdrop out in its own colour, so the page does not dip to grey on the way
      .to(root.current, { backgroundColor: getComputedStyle(root.current!).backgroundColor.replace(/rgba?\(([^,]+),([^,]+),([^,)]+).*$/, "rgba($1,$2,$3,0)"), duration: 0.45, ease: "power2.out" }, "-=0.25")
      .to(path.current, { opacity: 0, duration: 0.3 }, "-=0.1");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  const sources = status?.sources ?? {};
  return (
    <div className="preloader" ref={root} aria-busy="true" aria-label="Loading FLO Operations">
      <svg aria-hidden="true">
        <path ref={path} className="bracket" d={pathOf(start)} strokeWidth={ART.stroke * box.s} />
      </svg>
      <div ref={mark} style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, opacity: 0 }}>
        <Wordmark variant="full" height={box.h} />
      </div>
      <div className="sources" style={{ top: box.y + box.h + 28 }}>
        {SOURCE_ORDER.map((k) => {
          const s = sources[k];
          const cls = s ? (s.ok ? "ok" : s.error && !s.stale ? "bad" : "ok") : "";
          return (
            <span key={k} className={cls}>
              <i />
              {SOURCE_NAMES[k]}
            </span>
          );
        })}
      </div>
    </div>
  );
}
