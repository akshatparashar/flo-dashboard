import { ArrowLeft, ArrowUpRight, Moon, Sun } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStatus } from "../api/hooks";
import { Wordmark } from "../components/Brand";
import { ago } from "../lib/format";
import { useTheme } from "../lib/theme";
import { DASHBOARD, LABELS, markEntered } from "./brands";
import { LogoMark } from "./LogoMark";
import { gsap, reduced, useGSAP } from "./motion";
import "./world.css";

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
  stock_ageing: "Stock ageing",
};

interface Box {
  x: number; // centre
  y: number;
}

interface Link {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  parent: number; // the label this one hangs from, or -1 for the core
}

interface Layout {
  orbit: boolean;
  w: number;
  h: number;
  cx: number;
  cy: number;
  tileW: number;
  tileH: number;
  coreW: number;
  coreH: number;
  spots: Box[]; // one per label, in LABELS order
  links: Link[]; // one per label: a short stitch across the gap to its neighbour nearer the core
}

/*
  A 7 x 4 grid. The core fills the middle three columns of the two middle rows; the 22 labels fill the cells
  around it, nearest first. Each label is stitched to the neighbour one step nearer the core, so every link
  runs straight across a gap and none crosses a logo.
*/
const COLS = 7;
const ROWS = 4;
const CELLS: [c: number, r: number, pc: number, pr: number][] = [
  // touching the core (parent -1 is marked by pc = -1)
  [2, 0, -1, 0], [3, 0, -1, 0], [4, 0, -1, 0], [5, 1, -1, 0], [5, 2, -1, 0],
  [4, 3, -1, 0], [3, 3, -1, 0], [2, 3, -1, 0], [1, 2, -1, 0], [1, 1, -1, 0],
  // the corners of the inner ring
  [1, 0, 2, 0], [5, 0, 4, 0], [5, 3, 4, 3], [1, 3, 2, 3],
  // the outer columns
  [6, 0, 5, 0], [6, 1, 5, 1], [6, 2, 5, 2], [6, 3, 5, 3], [0, 3, 1, 3], [0, 2, 1, 2], [0, 1, 1, 1], [0, 0, 1, 0],
];

function computeLayout(w: number, h: number): Layout {
  const orbit = w >= 900 && h >= 500;
  const padX = Math.max(24, Math.min(56, w * 0.035));
  const padY = 8;
  const cellW = (w - padX * 2) / COLS;
  const cellH = (h - padY * 2) / ROWS;
  const gap = Math.round(Math.max(14, Math.min(24, cellW * 0.11)));
  const tileW = cellW - gap;
  const tileH = cellH - gap;
  const coreW = cellW * 3 - gap;
  const coreH = cellH * 2 - gap;
  const cx = w / 2;
  const cy = h / 2;
  const at = (c: number, r: number): Box => ({ x: padX + cellW * (c + 0.5), y: padY + cellH * (r + 0.5) });
  const spots = CELLS.slice(0, LABELS.length).map(([c, r]) => at(c, r));
  const index = (c: number, r: number) => CELLS.findIndex(([cc, rr]) => cc === c && rr === r);
  const links = CELLS.slice(0, LABELS.length).map(([c, r, pc, pr]): Link => {
    const me = at(c, r);
    if (pc >= 0) {
      // a neighbour in the same row
      const s = Math.sign(pc - c);
      return { x1: me.x + (s * tileW) / 2, y1: me.y, x2: me.x + s * (tileW / 2 + gap), y2: me.y, parent: index(pc, pr) };
    }
    if (r === 0 || r === ROWS - 1) {
      const s = r === 0 ? 1 : -1;
      return { x1: me.x, y1: me.y + (s * tileH) / 2, x2: me.x, y2: me.y + s * (tileH / 2 + gap), parent: -1 };
    }
    const s = c < COLS / 2 ? 1 : -1;
    return { x1: me.x + (s * tileW) / 2, y1: me.y, x2: me.x + s * (tileW / 2 + gap), y2: me.y, parent: -1 };
  });
  return { orbit, w, h, cx, cy, tileW, tileH, coreW, coreH, spots, links };
}

function useSize(el: React.RefObject<HTMLElement | null>) {
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight - 140 });
  useLayoutEffect(() => {
    if (!el.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el.current);
    return () => ro.disconnect();
  }, [el]);
  return size;
}

export default function World() {
  const root = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { resolved, toggle } = useTheme();
  const status = useStatus();
  const { w, h } = useSize(stage);
  const L = useMemo(() => computeLayout(w, h), [w, h]);
  const [arrived, setArrived] = useState(false);
  const busy = useRef(false);

  useEffect(() => {
    document.title = "FLO World";
  }, []);

  // the labels burst out of the centre, fly around, and settle into their places
  useGSAP(
    () => {
      if (w < 10) return;
      const tiles = gsap.utils.toArray<HTMLElement>(".w-tile");
      const core = root.current!.querySelector<HTMLElement>(".w-core")!;
      if (reduced()) {
        gsap.set([...tiles, core, ".w-rings", ".w-head > *", ".w-foot > *"], { opacity: 1 });
        setArrived(true);
        return;
      }
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const tl = gsap.timeline({ onComplete: () => setArrived(true) });
      tl.from(".w-head > *", { opacity: 0, y: -12, stagger: 0.06, duration: 0.7, ease: "power3.out" }, 0.2);
      tl.fromTo(core, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 1.2, ease: "expo.out" }, 0);
      tiles.forEach((el, i) => {
        const r = el.getBoundingClientRect();
        const dx = vw / 2 - (r.left + r.width / 2);
        const dy = vh / 2 - (r.top + r.height / 2);
        const sx = dx + gsap.utils.random(-vw * 0.42, vw * 0.42);
        const sy = dy + gsap.utils.random(-vh * 0.38, vh * 0.38);
        const at = 0.15 + i * 0.045;
        gsap.set(el, { x: dx, y: dy, scale: 0.2, opacity: 0, rotation: gsap.utils.random(-50, 50) });
        tl.to(el, { opacity: 1, duration: 0.3, ease: "none" }, at)
          .to(el, { scale: 1, duration: 1.3, ease: "expo.out" }, at)
          .to(el, { rotation: 0, duration: 1.9, ease: "power2.inOut" }, at)
          .to(
            el,
            {
              motionPath: { path: [{ x: dx, y: dy }, { x: sx, y: sy }, { x: 0, y: 0 }], curviness: 1.6 },
              duration: 1.9,
              ease: "power2.inOut",
            },
            at,
          );
      });
      tl.from(".w-foot > *", { opacity: 0, y: 12, stagger: 0.08, duration: 0.7, ease: "power3.out" }, 2.2);
    },
    { scope: root, dependencies: [w > 10, L.orbit] },
  );

  // once settled: the stitches draw in, and signals hop from label to label in towards the core
  useGSAP(
    () => {
      if (!arrived || !L.orbit || reduced()) return;
      const lines = gsap.utils.toArray<SVGLineElement>(".w-link");
      lines.forEach((ln) => {
        const len = Math.hypot(+ln.getAttribute("x2")! - +ln.getAttribute("x1")!, +ln.getAttribute("y2")! - +ln.getAttribute("y1")!);
        gsap.fromTo(ln, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.6, ease: "power2.out", delay: gsap.utils.random(0, 0.6) });
      });
      const tiles = root.current?.querySelectorAll<HTMLElement>(".w-tile");
      const dots = gsap.utils.toArray<SVGCircleElement>(".w-signal");
      const hop = (dot: SVGCircleElement, i: number) => {
        const k = L.links[i];
        const tile = tiles?.[i];
        tile?.classList.add("ping");
        gsap.fromTo(
          dot,
          { attr: { cx: k.x1, cy: k.y1 }, opacity: 0 },
          {
            attr: { cx: k.x2, cy: k.y2 },
            keyframes: { opacity: [0, 1, 1, 0] },
            duration: 0.45,
            delay: 0.25,
            ease: "power1.inOut",
            onComplete: () => {
              tile?.classList.remove("ping");
              if (k.parent >= 0) return hop(dot, k.parent);
              gsap.fromTo(".w-core", { "--hit": 1 }, { "--hit": 0, duration: 0.8, ease: "power2.out" });
              gsap.delayedCall(gsap.utils.random(0.4, 1.8), () => send(dot));
            },
          },
        );
      };
      // start from an outer label, so the signal crosses the whole world
      const send = (dot: SVGCircleElement) => hop(dot, 10 + Math.floor(Math.random() * (L.links.length - 10)));
      dots.forEach((d, k) => gsap.delayedCall(0.8 + k * 0.7, () => send(d)));
    },
    { scope: root, dependencies: [arrived, L.orbit, L.w, L.h], revertOnUpdate: true },
  );

  // the status line types itself through each sheet's real sync state
  const lines = useMemo(() => {
    const src = status.data?.sources ?? {};
    const out = ["FLO intelligence online."];
    for (const [k, s] of Object.entries(src)) out.push(`${SOURCE_NAMES[k] ?? s.name}: ${s.ok ? "in sync" : "needs a look"}, ${s.synced_at ? ago(s.synced_at) : "waiting"}.`);
    return out;
  }, [status.data]);
  useGSAP(
    () => {
      const el = root.current?.querySelector(".w-type");
      if (!el) return;
      if (reduced()) {
        el.textContent = lines[0];
        return;
      }
      let i = 0;
      const next = () => {
        gsap.to(el, { duration: 1.1, scrambleText: { text: lines[i % lines.length], chars: "01", speed: 0.5, revealDelay: 0.2 }, ease: "none" });
        i++;
      };
      next();
      const id = window.setInterval(next, 3600);
      return () => window.clearInterval(id);
    },
    { scope: root, dependencies: [lines.join("|")] },
  );

  const go = useCallback(
    (el: HTMLElement, to: string, live: boolean) => {
      if (busy.current) return;
      busy.current = true;
      if (live) markEntered();
      if (reduced()) {
        navigate(to);
        return;
      }
      const r = el.getBoundingClientRect();
      const s = Math.max(window.innerWidth / r.width, window.innerHeight / r.height) * 1.2;
      const others = gsap.utils.toArray<HTMLElement>(".w-tile, .w-core, .w-rings, .w-head, .w-foot").filter((o) => o !== el && !o.contains(el));
      gsap
        .timeline({ onComplete: () => navigate(to) })
        .to(others, { opacity: 0, scale: 0.96, duration: 0.45, ease: "power2.in" }, 0)
        .to(el, { x: window.innerWidth / 2 - (r.left + r.width / 2), y: window.innerHeight / 2 - (r.top + r.height / 2), duration: 0.55, ease: "power3.inOut" }, 0.1)
        .to(el, { scale: s, opacity: 0, duration: 0.6, ease: "expo.in" }, 0.55);
    },
    [navigate],
  );

  const press = (e: React.MouseEvent<HTMLAnchorElement>, to: string, live: boolean) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    go(e.currentTarget, to, live);
  };

  const sources = Object.values(status.data?.sources ?? {});
  const okCount = sources.filter((s) => s.ok).length;
  const logoW = (w: number, h: number, room: number) => Math.round(Math.min(w, (h - room) * DASHBOARD.ratio));
  const orbitStyle = (i: number): React.CSSProperties | undefined =>
    L.orbit
      ? ({
          position: "absolute",
          left: L.spots[i].x - L.tileW / 2,
          top: L.spots[i].y - L.tileH / 2,
          width: L.tileW,
          height: L.tileH,
          "--logo": `${logoW(L.tileW * 0.74, L.tileH, 44)}px`,
        } as React.CSSProperties)
      : undefined;

  return (
    <div className={`world${L.orbit ? " w-orbit" : " w-grid"}${arrived ? " arrived" : ""}`} ref={root}>
      <header className="w-head">
        <Link to="/welcome" className="w-back" aria-label="Back to the FLO home page">
          <ArrowLeft aria-hidden="true" />
          <Wordmark variant="letters" height={16} />
        </Link>
        <div className="w-title">
          <h1>FLO World</h1>
          <p className="w-type" aria-live="off">
            FLO intelligence online.
          </p>
        </div>
        <button className="w-icon" onClick={toggle} aria-label={resolved === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
          {resolved === "dark" ? <Sun /> : <Moon />}
        </button>
      </header>

      <div className="w-stage" ref={stage}>
        {L.orbit && (
          <svg className="w-rings" width={L.w} height={L.h} aria-hidden="true">
            {L.links.map((k, i) => (
              <line key={i} className="w-link" x1={k.x1} y1={k.y1} x2={k.x2} y2={k.y2} />
            ))}
            {[0, 1, 2].map((k) => (
              <circle key={k} className="w-signal" r="3" cx={L.cx} cy={L.cy} opacity="0" />
            ))}
          </svg>
        )}

        <Link
          to="/"
          className="w-core"
          aria-label="FLO Dashboard, live. Open it."
          onClick={(e) => press(e, "/", true)}
          style={
            L.orbit
              ? ({ position: "absolute", left: L.cx - L.coreW / 2, top: L.cy - L.coreH / 2, width: L.coreW, height: L.coreH, "--logo": `${logoW(Math.min(340, L.coreW * 0.62), L.coreH, 120)}px` } as React.CSSProperties)
              : undefined
          }
        >
          <span className="core-live">
            <i aria-hidden="true" />
            Live
          </span>
          <LogoMark label={DASHBOARD} className="core-logo" />
          <span className="core-meta">
            {sources.length ? `${okCount} of ${sources.length} sheets in sync` : "Connecting to the sheets"}
            <ArrowUpRight aria-hidden="true" />
          </span>
        </Link>

        {LABELS.map((l, i) => (
          <Link key={l.slug} to={`/world/${l.slug}`} className="w-tile" style={orbitStyle(i)} aria-label={`FLO ${l.name}, coming soon`} onClick={(e) => press(e, `/world/${l.slug}`, false)}>
            <LogoMark label={l} className="tile-logo" />
            <span className="tile-state">Coming soon</span>
          </Link>
        ))}
      </div>

      <footer className="w-foot">
        <span>
          <b>23</b> modules
        </span>
        <span>
          <b>1</b> live
        </span>
        <span>
          <b>22</b> in the making
        </span>
        <span className="w-foot-hint">Choose a label to open it.</span>
      </footer>
    </div>
  );
}
