import { ArrowLeft, ArrowUpRight, Moon, Sun } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useTheme } from "../lib/theme";
import { labelBySlug, markEntered } from "./brands";
import { LogoMark } from "./LogoMark";
import { gsap, reduced, SplitText, useGSAP } from "./motion";
import "./world.css";

/** A label that is not built yet: its logo, a needle running a stitch line under it, and the way back. */
export default function Soon() {
  const { slug } = useParams();
  const label = labelBySlug(slug);
  const root = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { resolved, toggle } = useTheme();

  useEffect(() => {
    if (label) document.title = `FLO ${label.name} · Coming soon`;
  }, [label]);

  useGSAP(
    () => {
      if (!label) return;
      const rm = reduced();
      const head = new SplitText(".soon h1", { type: "words", mask: "words" });
      if (rm) return () => head.revert();
      const tl = gsap.timeline();
      tl.fromTo(".soon-logo", { opacity: 0, scale: 1.25, filter: "blur(8px)" }, { opacity: 1, scale: 1, filter: "blur(0px)", duration: 1.3, ease: "expo.out" })
        .from(head.words, { yPercent: 110, stagger: 0.06, duration: 0.9, ease: "expo.out" }, 0.5)
        .from(".soon p, .soon-actions > *", { opacity: 0, y: 14, stagger: 0.08, duration: 0.8, ease: "power3.out" }, 0.75);
      // the stitch line sews itself, over and over, under the logo
      const stitches = gsap.utils.toArray<SVGLineElement>(".stitch line");
      const needle = root.current!.querySelector(".stitch .s-needle");
      const sew = gsap.timeline({ repeat: -1, repeatDelay: 0.6, delay: 1 });
      sew
        .set(stitches, { opacity: 0 })
        .fromTo(needle, { x: -40 }, { x: 640, duration: 3.4, ease: "none" }, 0)
        .to(stitches, { opacity: 1, duration: 0.12, stagger: 3.4 / stitches.length, ease: "none" }, 0.05)
        .to(stitches, { opacity: 0, duration: 0.5, stagger: 0.02 }, "+=0.8");
      gsap.to(".soon-halo", { rotation: 360, duration: 40, ease: "none", repeat: -1 });
      return () => head.revert();
    },
    { scope: root, dependencies: [slug] },
  );

  if (!label) return <Navigate to="/world" replace />;

  const openDashboard = () => {
    markEntered();
    navigate("/");
  };

  return (
    <div className="soon-page" ref={root}>
      <header className="w-head">
        <Link to="/world" className="w-back" aria-label="Back to FLO World">
          <ArrowLeft aria-hidden="true" />
          FLO World
        </Link>
        <span />
        <button className="w-icon" onClick={toggle} aria-label={resolved === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
          {resolved === "dark" ? <Sun /> : <Moon />}
        </button>
      </header>
      <main className="soon">
        <div className="soon-mark">
          <svg className="soon-halo" viewBox="0 0 200 200" aria-hidden="true">
            <circle cx="100" cy="100" r="96" />
          </svg>
          <LogoMark label={label} className="soon-logo" />
        </div>
        <svg className="stitch" viewBox="0 0 600 24" aria-hidden="true">
          {Array.from({ length: 24 }, (_, i) => (
            <line key={i} x1={i * 25 + 4} y1="12" x2={i * 25 + 17} y2="12" />
          ))}
          <g className="s-needle">
            <path d="M 40 12 L 4 11 Q -2 11 -2 12 Q -2 13 4 13 Z" />
          </g>
        </svg>
        <h1>FLO {label.name} is being stitched in.</h1>
        <p>This label gets its own room in the FLO system soon. Until then, everything the house runs on lives in the FLO Dashboard.</p>
        <div className="soon-actions">
          <button className="w-btn primary" onClick={openDashboard}>
            Open FLO Dashboard
            <ArrowUpRight aria-hidden="true" />
          </button>
          <Link className="w-btn ghost" to="/world">
            Back to FLO World
          </Link>
        </div>
      </main>
    </div>
  );
}
