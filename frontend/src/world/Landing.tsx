import { ArrowRight, ArrowUp, ArrowUpRight, Moon, Sun } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDashboard, useStatus } from "../api/hooks";
import type { Kpi, OverviewData, StatusData } from "../api/types";
import { Wordmark } from "../components/Brand";
import { ago, fmtKpi } from "../lib/format";
import { useTheme } from "../lib/theme";
import { DASHBOARD, LABELS, markEntered } from "./brands";
import { LogoMark } from "./LogoMark";
import { gsap, reduced, ScrollTrigger, SplitText, useGSAP } from "./motion";
import { NeedleFLO, STITCH, type NeedleHandle } from "./NeedleFLO";
import "./world.css";

const STAGES = [
  {
    name: "Design",
    line: "Designers sketch, clients choose, and the target shows who is ahead this month.",
    pages: [
      { to: "/designers", label: "Designers" },
      { to: "/target", label: "Designer order target" },
      { to: "/clients", label: "Clients order status" },
    ],
  },
  {
    name: "Sample",
    line: "Every sample is followed from cutting to approval, by designer and by date.",
    pages: [{ to: "/samples", label: "Samples" }],
  },
  {
    name: "Fabric",
    line: "Fabric is ordered, received and priced vendor by vendor, with every late PO in view.",
    pages: [
      { to: "/fabric-po", label: "Fabric PO" },
      { to: "/vendor-rate", label: "Vendor rate" },
    ],
  },
  {
    name: "Production",
    line: "Fabricators stitch; each piece is counted out, counted back and aged in stock.",
    pages: [
      { to: "/production", label: "Production" },
      { to: "/fabricators", label: "Fabricators" },
      { to: "/stock-ageing", label: "Stock ageing" },
    ],
  },
  {
    name: "Delivery",
    line: "Promises kept on time, sales in and out, and the day's work handed to the right person.",
    pages: [
      { to: "/flo-future", label: "FLO Future" },
      { to: "/in-out-sale", label: "In/Out sale" },
      { to: "/daily-delegation", label: "Daily delegation" },
    ],
  },
];

const FOOT = [
  {
    title: "Operations",
    links: [
      { to: "/", label: "Overview" },
      { to: "/production", label: "Production" },
      { to: "/fabricators", label: "Fabricators" },
      { to: "/fabric-po", label: "Fabric PO" },
      { to: "/stock-ageing", label: "Stock ageing" },
    ],
  },
  {
    title: "Design and sales",
    links: [
      { to: "/designers", label: "Designers" },
      { to: "/clients", label: "Clients order status" },
      { to: "/samples", label: "Samples" },
      { to: "/target", label: "Designer order target" },
      { to: "/flo-future", label: "FLO Future" },
    ],
  },
  {
    title: "FLO world",
    links: [
      { to: "/world", label: "All 23 modules" },
      { to: "/world/vibe", label: "FLO Vibe" },
      { to: "/world/men", label: "FLO Men" },
      { to: "/world/curve", label: "FLO Curve" },
      { to: "/world/drape", label: "FLO Drape" },
    ],
  },
];

const ASK = ["Which fabric POs are overdue?", "How many orders are pending with fabricators?", "Who is the top designer this month?"];

interface LiveCard {
  kpi: Kpi;
  to: string;
  area: string;
}

function pickCards(o: OverviewData | undefined): LiveCard[] {
  if (!o) return [];
  const s = o.sections;
  const out: LiveCard[] = [];
  const add = (k: Kpi | undefined, to: string, area: string) => k && out.push({ kpi: k, to, area });
  add(s.orders?.kpis[0], "/production", "Orders");
  add(s.orders?.kpis[1], "/production", "Orders");
  add(s.po?.kpis[0], "/fabric-po", "Fabric");
  add(s.samples?.kpis[0], "/samples", "Samples");
  add(s.stock?.kpis[0], "/fabricators", "Fabricators");
  return out.slice(0, 5);
}

function syncLine(st: StatusData | undefined): { ok: number; total: number; when: string } | null {
  if (!st) return null;
  const all = Object.values(st.sources);
  const ok = all.filter((s) => s.ok).length;
  const latest = all.map((s) => s.synced_at).filter(Boolean).sort().pop() ?? null;
  return { ok, total: all.length, when: latest ? ago(latest) : "just now" };
}

export default function Landing({ ready = true }: { ready?: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const needle = useRef<NeedleHandle>(null);
  const navigate = useNavigate();
  const { resolved, toggle } = useTheme();
  const status = useStatus();
  const overview = useDashboard<OverviewData>("/overview", {});
  const cards = useMemo(() => pickCards(overview.data), [overview.data]);
  const sync = syncLine(status.data);
  const leaving = useRef(false); // a ref, not state: re-rendering the whole page on the click made the dive stutter

  useEffect(() => {
    document.title = "FLO · Let the fashion flo";
    // fetch FLO World ahead of the click, so the zoom lands straight in it
    void import("./World");
    void import("./Soon");
  }, []);

  // the thread through the stages runs from knot to knot, dipping between cards
  const stagesRef = useRef<HTMLDivElement>(null);
  const [run, setRun] = useState("");
  useEffect(() => {
    const el = stagesRef.current;
    if (!el) return;
    const draw = () => {
      // layout positions, not on-screen ones: the cards may be mid-entrance (transformed) when this runs
      const box = el.getBoundingClientRect();
      const pts: number[][] = [];
      for (const k of el.querySelectorAll<HTMLElement>(".knot")) {
        const card = k.offsetParent as HTMLElement | null;
        if (!card) return; // detached or hidden (leaving the page)
        pts.push([card.offsetLeft + k.offsetLeft + k.offsetWidth / 2, card.offsetTop + k.offsetTop + k.offsetHeight / 2]);
      }
      if (pts.length < 2 || pts[1][1] - pts[0][1] > 20) return setRun(""); // stacked layout: no thread
      let d = `M ${-box.left} ${pts[0][1]} L ${pts[0][0]} ${pts[0][1]}`;
      for (let i = 1; i < pts.length; i++) {
        const [x0, y0] = pts[i - 1];
        const [x1, y1] = pts[i];
        const dip = i % 2 ? -34 : 30;
        d += ` C ${x0 + (x1 - x0) * 0.35} ${y0 + dip}, ${x0 + (x1 - x0) * 0.65} ${y1 + dip}, ${x1} ${y1}`;
      }
      const [lx, ly] = pts[pts.length - 1];
      d += ` C ${lx + 120} ${ly - 30}, ${box.width} ${ly + 20}, ${window.innerWidth - box.left} ${ly}`;
      setRun(d);
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // hero entrance, after the preloader has gone
  useGSAP(
    () => {
      if (!ready) return;
      const rm = reduced();
      const line = new SplitText(".hero-line", { type: "words", mask: "words" });
      const tl = gsap.timeline({ delay: 0.1 });
      tl.add(needle.current!.play(), 0);
      if (rm) {
        gsap.set([".hero-line", ".hero-sub", ".hero-cta", ".hero-corner", ".land-nav"], { opacity: 1, y: 0 });
        return;
      }
      tl.from(".land-nav > *", { opacity: 0, y: -10, stagger: 0.06, duration: 0.7, ease: "power3.out" }, 0.4);
      // the words come in as the needle leaves the O
      const t = 0.1 + STITCH * 0.72;
      tl.from(line.words, { yPercent: 110, duration: 0.9, stagger: 0.07, ease: "expo.out" }, t)
        .from(".hero-sub", { opacity: 0, y: 14, duration: 0.8, ease: "power3.out" }, t + 0.35)
        .from(".hero-cta", { opacity: 0, y: 14, scale: 0.96, duration: 0.8, ease: "expo.out" }, t + 0.55)
        .from(".hero-corner", { opacity: 0, duration: 0.8, stagger: 0.1 }, t + 0.8);
      return () => line.revert();
    },
    { scope: root, dependencies: [ready] },
  );

  // section entrances and the scroll-drawn thread
  useGSAP(
    () => {
      if (reduced()) return;
      gsap.utils.toArray<HTMLElement>(".reveal").forEach((sec) => {
        const parts = sec.querySelectorAll(".rv");
        gsap.from(parts, {
          opacity: 0,
          y: 28,
          duration: 0.9,
          stagger: 0.08,
          ease: "power3.out",
          scrollTrigger: { trigger: sec, start: "top 78%", once: true },
        });
      });
      // the bar slips away while reading down, and comes back on the way up
      ScrollTrigger.create({
        start: 120,
        onUpdate: (st) => root.current?.querySelector(".land-nav")?.classList.toggle("away", st.direction === 1 && st.scroll() > 400),
      });
      gsap.from(".stage", {
        opacity: 0,
        y: 36,
        stagger: 0.12,
        duration: 0.9,
        ease: "power3.out",
        scrollTrigger: { trigger: ".stages", start: "top 75%", once: true },
      });
      // the labels drift in two rows, opposite ways
      gsap.utils.toArray<HTMLElement>(".marquee-track").forEach((t, i) => {
        gsap.fromTo(t, { xPercent: i % 2 ? -50 : 0 }, { xPercent: i % 2 ? 0 : -50, duration: 60, ease: "none", repeat: -1 });
      });
      gsap.from(".foot-flo", { yPercent: 40, opacity: 0, duration: 1.2, ease: "expo.out", scrollTrigger: { trigger: ".foot-flo", start: "top 95%", once: true } });
      gsap.from(".foot-brand > *, .foot-cols > div", { opacity: 0, y: 24, stagger: 0.07, duration: 0.9, ease: "power3.out", scrollTrigger: { trigger: ".land-foot", start: "top 80%", once: true } });
      ScrollTrigger.refresh();
    },
    { scope: root },
  );

  useGSAP(
    () => {
      const p = root.current?.querySelector<SVGPathElement>(".stage-thread path");
      if (!p || !run || reduced()) return;
      const len = p.getTotalLength();
      gsap.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, ease: "none", scrollTrigger: { trigger: ".stages", start: "top 80%", end: "top 25%", scrub: 0.6 } });
    },
    { scope: root, dependencies: [run], revertOnUpdate: true },
  );

  // live numbers count up the first time they arrive
  useGSAP(
    () => {
      if (!cards.length || reduced()) return;
      root.current?.querySelectorAll<HTMLElement>("[data-count]").forEach((el) => {
        const target = Number(el.dataset.count);
        const fmt = el.dataset.fmt as Kpi["format"];
        const o = { v: 0 };
        gsap.to(o, {
          v: target,
          duration: 1.6,
          ease: "expo.out",
          scrollTrigger: { trigger: el, start: "top 90%", once: true },
          onUpdate: () => {
            el.textContent = fmtKpi(fmt === "int" || fmt === "inr" ? Math.round(o.v) : o.v, fmt).value;
          },
        });
      });
    },
    { scope: root, dependencies: [cards.length] },
  );

  // a card leans toward the pointer
  const tilt = (e: React.PointerEvent<HTMLElement>) => {
    if (reduced() || e.pointerType !== "mouse") return;
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    gsap.to(el, { rotateY: x * 6, rotateX: -y * 6, y: -4, duration: 0.5, ease: "power3.out", transformPerspective: 900 });
    el.style.setProperty("--mx", `${(x + 0.5) * 100}%`);
    el.style.setProperty("--my", `${(y + 0.5) * 100}%`);
  };
  const untilt = (e: React.PointerEvent<HTMLElement>) => gsap.to(e.currentTarget, { rotateY: 0, rotateX: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.6)" });

  // the button follows the pointer a little
  const magnet = (e: React.PointerEvent<HTMLElement>) => {
    if (reduced() || e.pointerType !== "mouse") return;
    const r = e.currentTarget.getBoundingClientRect();
    gsap.to(e.currentTarget, { x: (e.clientX - r.left - r.width / 2) * 0.25, y: (e.clientY - r.top - r.height / 2) * 0.35, duration: 0.4, ease: "power3.out" });
  };
  const unmagnet = (e: React.PointerEvent<HTMLElement>) => gsap.to(e.currentTarget, { x: 0, y: 0, duration: 0.8, ease: "elastic.out(1, 0.5)" });

  const enter = () => {
    if (leaving.current) return;
    leaving.current = true;
    window.scrollTo({ top: 0, behavior: reduced() ? "auto" : "smooth" });
    const tl = gsap.timeline({ onComplete: () => navigate("/world") });
    tl.to([".hero-line", ".hero-sub", ".hero-cta", ".hero-corner", ".land-nav"], { opacity: 0, y: -12, duration: 0.3, stagger: 0.03, ease: "power2.in" }, window.scrollY > 40 ? 0.45 : 0).add(needle.current!.enter(), "-=0.2");
  };

  const openDashboard = () => {
    markEntered();
    navigate("/");
  };

  return (
    <div className={`land${ready ? " is-ready" : ""}`} ref={root}>
      <a className="skip" href="#system">
        Skip to content
      </a>
      <header className="land-nav">
        <Link to="/welcome" className="land-brand" aria-label="FLO home">
          <Wordmark variant="letters" height={20} />
        </Link>
        <nav className="land-links" aria-label="Sections">
          <a href="#system">The system</a>
          <a href="#thread">The thread</a>
          <a href="#labels">The labels</a>
        </nav>
        <div className="land-actions">
          <button className="w-icon" onClick={toggle} aria-label={resolved === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
            {resolved === "dark" ? <Sun /> : <Moon />}
          </button>
          <button className="w-btn ghost" onClick={openDashboard}>
            Open dashboard
          </button>
        </div>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <h1 id="hero-title" className="hero-flo">
          <span className="sr-only">FLO</span>
          <NeedleFLO ref={needle} />
        </h1>
        <div className="hero-copy">
          <p className="hero-line">Let the fashion flo.</p>
          <p className="hero-sub">FLO India's own intelligence. Every order, sample, fabric roll and delivery, read live from the sheets and answered in one place.</p>
          <button className="w-btn primary hero-cta" onClick={enter} onPointerMove={magnet} onPointerLeave={unmagnet}>
            Enter the FLO world
            <ArrowRight aria-hidden="true" />
          </button>
        </div>
        <div className="hero-corner left">
          Fashion, lifestyle, outfit
          <br />
          Jaipur, India
        </div>
        <div className="hero-corner right" aria-live="polite">
          <span className={`pulse${sync && sync.ok < sync.total ? " warn" : ""}`} aria-hidden="true" />
          {sync ? (
            <>
              {sync.ok} of {sync.total} sheets in sync
              <br />
              updated {sync.when}
            </>
          ) : (
            <>
              Connecting to the sheets
              <br />
              one moment
            </>
          )}
        </div>
      </section>

      <section id="system" className="sec reveal" aria-labelledby="system-title">
        <div className="sec-head">
          <h2 id="system-title" className="rv">
            The whole house, live.
          </h2>
          <p className="rv">These numbers are read from the FLO sheets right now. Nobody typed them in; when a sheet changes, this changes within a minute.</p>
        </div>
        <div className="bento">
          {cards.length === 0 &&
            Array.from({ length: 5 }, (_, i) => (
              <div key={i} className={`card live-card skeleton${i === 0 ? " big" : ""}`} aria-hidden="true" />
            ))}
          {cards.map((c, i) => {
            const f = fmtKpi(c.kpi.value, c.kpi.format);
            const n = typeof c.kpi.value === "number" ? c.kpi.value : null;
            return (
              <Link key={c.kpi.id + i} to={c.to} onClick={markEntered} className={`card live-card rv${i === 0 ? " big" : ""}`} onPointerMove={tilt} onPointerLeave={untilt}>
                <span className="lc-area">{c.area}</span>
                <span className="lc-value">
                  <span data-count={n ?? undefined} data-fmt={c.kpi.format}>
                    {f.value}
                  </span>
                  {f.unit && <small>{f.unit}</small>}
                </span>
                <span className="lc-label">{c.kpi.label}</span>
                {c.kpi.hint && <span className="lc-hint">{c.kpi.hint}</span>}
                <ArrowUpRight className="lc-go" aria-hidden="true" />
              </Link>
            );
          })}
          <div className="card ask-card rv" onPointerMove={tilt} onPointerLeave={untilt}>
            <h3>Ask in plain words.</h3>
            <p>The FLO assistant reads the same sheets. Open the dashboard and ask it anything, the way you would ask a colleague.</p>
            <ul>
              {ASK.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section id="thread" className="sec band reveal" aria-labelledby="thread-title">
        <div className="sec-head">
          <h2 id="thread-title" className="rv">
            One thread, design to delivery.
          </h2>
          <p className="rv">Each stage of a garment has its own page in the system. Follow the thread to the one you need.</p>
        </div>
        <div className="stages" ref={stagesRef}>
          {run && (
            <svg className="stage-thread" aria-hidden="true">
              <path d={run} />
            </svg>
          )}
          {STAGES.map((s) => (
            <article key={s.name} className="stage card" onPointerMove={tilt} onPointerLeave={untilt}>
              <span className="knot" aria-hidden="true" />
              <h3>{s.name}</h3>
              <p>{s.line}</p>
              <ul>
                {s.pages.map((p) => (
                  <li key={p.to}>
                    <Link to={p.to} onClick={markEntered}>
                      {p.label}
                      <ArrowUpRight aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section id="labels" className="sec reveal" aria-labelledby="labels-title">
        <div className="sec-head">
          <h2 id="labels-title" className="rv">
            Twenty-two labels. One world.
          </h2>
          <p className="rv">Every FLO label gets its own room in the system. The dashboard is open today; the others are being stitched in, one by one.</p>
        </div>
        <div className="marquee rv" aria-label="The FLO labels">
          {[[DASHBOARD, ...LABELS.slice(0, 11)], LABELS.slice(11)].map((list, row) => (
            <div key={row} className="marquee-row">
              {/* the set twice, so a -50% shift loops without a seam */}
              <div className="marquee-track">
                {[...list, ...list].map((l, i) => (
                  <LogoMark key={l.slug + i} label={l} className="mq-logo" decorative={i >= list.length} />
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="labels-cta rv">
          <button className="w-btn primary" onClick={enter} onPointerMove={magnet} onPointerLeave={unmagnet}>
            Enter the FLO world
            <ArrowRight aria-hidden="true" />
          </button>
        </div>
      </section>

      <section className="sec house reveal" aria-labelledby="house-title">
        <h2 id="house-title" className="house-quote rv">
          Where modern style embraces timeless tradition.
        </h2>
        <div className="card house-card rv" onPointerMove={tilt} onPointerLeave={untilt}>
          <h3>FLO India</h3>
          <dl>
            <div>
              <dt>Founder</dt>
              <dd>Arihant Jain</dd>
            </div>
            <div>
              <dt>What we make</dt>
              <dd>Indian wear, indo-western and ethnic clothing for men, women and children</dd>
            </div>
            <div>
              <dt>Where</dt>
              <dd>S-4, Kartarpura Industrial Area, Bais Godam, Jaipur 302006</dd>
            </div>
          </dl>
        </div>
      </section>

      <footer className="land-foot" aria-labelledby="foot-title">
        <div className="foot-panel">
          <div className="foot-top">
            <div className="foot-brand">
              <h2 id="foot-title" className="foot-line">
                Let the fashion flo.
              </h2>
              <p>FLO India's own intelligence: every order, sample, fabric roll and delivery, read live from the sheets.</p>
              <button className="foot-cta" onClick={enter}>
                Enter the FLO world
                <ArrowRight aria-hidden="true" />
              </button>
            </div>
            <nav className="foot-cols" aria-label="Footer">
              {FOOT.map((col) => (
                <div key={col.title}>
                  <h3>{col.title}</h3>
                  <ul>
                    {col.links.map((l) => (
                      <li key={l.to}>
                        <Link to={l.to} onClick={l.to.startsWith("/world") ? undefined : markEntered}>
                          {l.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              <div>
                <h3>The house</h3>
                <address>
                  FLO India
                  <br />
                  S-4, Kartarpura Industrial Area
                  <br />
                  Bais Godam, Jaipur 302006
                </address>
              </div>
            </nav>
          </div>
          <div className="foot-flo" aria-hidden="true">
            <span className="foot-mark" />
          </div>
          <div className="foot-row">
            <span>© {new Date().getFullYear()} FLO India. All rights reserved.</span>
            <span>Internal system · a read-only view of the FLO Google Sheets</span>
            <button className="foot-top-btn" onClick={() => window.scrollTo({ top: 0, behavior: reduced() ? "auto" : "smooth" })}>
              Back to top
              <ArrowUp aria-hidden="true" />
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
