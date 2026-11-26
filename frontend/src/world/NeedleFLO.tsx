import { forwardRef, useImperativeHandle, useRef } from "react";
import { gsap, reduced } from "./motion";

/*
  The FLO letters (the logo's own artwork, 450 x 165) with a needle that stitches a thread through them:
  behind the F, over the L, behind the left of the O, through its counter and out over its right side.
  The thread is drawn twice: once under the letters, once over them clipped to the "over" stretches, so it
  really weaves. The needle is drawn the same way, so it disappears into the letters and comes back out.
*/

/** seconds the needle takes to stitch through the letters */
export const STITCH = 5.2;

const THREAD =
  "M -875 30 C -560 30, -240 150, 0 128 C 60 122, 100 132, 128 112 C 150 98, 160 70, 186 56 C 215 40, 245 70, 262 100 " +
  "C 280 130, 300 118, 330 104 C 370 86, 405 80, 432 74 C 520 56, 640 0, 860 -6 C 1040 -12, 1200 30, 1325 20";

// stretches where the thread runs over the letters (in letter units)
const FRONT = [
  [132, 258],
  [398, 1400],
];

export interface NeedleHandle {
  play: () => gsap.core.Timeline;
  /** zoom through the O's counter; resolves when done */
  enter: () => gsap.core.Timeline;
}

export const NeedleFLO = forwardRef<NeedleHandle, { id?: string }>(function NeedleFLO({ id = "flo" }, ref) {
  const svg = useRef<SVGSVGElement>(null);
  const backT = useRef<SVGPathElement>(null);
  const frontT = useRef<SVGPathElement>(null);
  const glowB = useRef<SVGPathElement>(null);
  const glowF = useRef<SVGPathElement>(null);
  const backN = useRef<SVGGElement>(null);
  const frontN = useRef<SVGGElement>(null);
  const letters = useRef<SVGGElement>(null);

  useImperativeHandle(ref, () => ({
    play() {
      const tl = gsap.timeline();
      const paths = [backT.current!, frontT.current!];
      const needles = [backN.current!, frontN.current!];
      const len = backT.current!.getTotalLength();
      if (reduced()) {
        gsap.set(paths, { strokeDasharray: "none", strokeDashoffset: 0 });
        gsap.set(letters.current, { opacity: 1 });
        gsap.set(needles, { opacity: 0 });
        return tl;
      }
      // The thread starts far off to the left (for wide screens). Begin at the screen's left edge instead, so the
      // needle is in view from the first frame rather than travelling unseen for a couple of seconds.
      const ctm = svg.current!.getScreenCTM();
      const edge = ctm ? -ctm.e / ctm.a - 30 : -Infinity;
      let from = 0;
      while (from < len && backT.current!.getPointAtLength(from).x < edge) from += 8;
      const f0 = Math.min(from / len, 0.6);
      gsap.set(paths, { strokeDasharray: len, strokeDashoffset: len * (1 - f0) });
      // hidden until it starts moving: before that it would sit unplaced at the top left of the letters
      gsap.set(needles, { opacity: 0 });
      // slow enough to follow the needle in, behind and out of each letter
      tl.fromTo(letters.current, { opacity: 0, scale: 1.035, transformOrigin: "50% 50%" }, { opacity: 1, scale: 1, duration: 1.4, ease: "expo.out" })
        .addLabel("stitch", 0.1) // the needle sets off straight away, while the letters are still fading in
        .to(paths, { strokeDashoffset: 0, duration: STITCH, ease: "sine.inOut" }, "stitch");
      tl.set(needles, { opacity: 1 }, "stitch+=0.05");
      for (const n of needles) {
        tl.to(
          n,
          {
            duration: STITCH,
            ease: "sine.inOut",
            motionPath: { path: backT.current!, align: backT.current!, alignOrigin: [1, 0.5], autoRotate: true, start: f0, end: 1 },
          },
          "stitch",
        );
      }
      tl.to(needles, { opacity: 0, duration: 0.6 }, "-=0.6");
      // afterwards a short glint keeps running along the thread, like a signal through a wire
      const gl = 120;
      gsap.set([glowB.current, glowF.current], { strokeDasharray: `${gl} ${len}`, strokeDashoffset: gl });
      tl.add(() => {
        gsap.fromTo([glowB.current, glowF.current], { strokeDashoffset: gl, opacity: 1 }, { strokeDashoffset: -len, duration: 6, ease: "sine.inOut", repeat: -1, repeatDelay: 2.4 });
      });
      return tl;
    },
    enter() {
      const tl = gsap.timeline();
      if (reduced()) return tl.to(svg.current, { opacity: 0, duration: 0.25 });
      // Zoom the letters' box as one GPU layer (will-change in world.css): scaling the SVG itself re-renders its mask, the thread's shadow
      // and the glint every frame, which is what made the dive into the O stutter. The O's counter centre sits at
      // 83.2% x 49.8% of the 450 x 165 letters.
      const wrap = svg.current!.parentElement!;
      gsap.killTweensOf([glowB.current, glowF.current]);
      svg.current!.classList.add("is-leaving");
      gsap.set(wrap, { transformOrigin: "83.2% 49.8%" });
      return tl
        .to(wrap, { scale: 18, duration: 0.9, ease: "expo.in", force3D: true })
        .to(wrap, { opacity: 0, duration: 0.3, ease: "power1.in" }, "-=0.3");
    },
  }));

  const mask = `${id}-letters`;
  const clip = `${id}-front`;
  return (
    <svg ref={svg} className="needle-flo" viewBox="-875 -60 2200 290" aria-hidden="true">
      <defs>
        <mask id={mask} style={{ maskType: "alpha" }} maskUnits="userSpaceOnUse" x="0" y="0" width="450" height="165">
          <image href="/brand/flo-letters-hi.png" x="0" y="0" width="450" height="165" />
        </mask>
        <clipPath id={clip}>
          {FRONT.map(([a, b]) => (
            <rect key={a} x={a} y="-200" width={b - a} height="600" />
          ))}
        </clipPath>
      </defs>
      <path ref={backT} className="thread" d={THREAD} />
      <path ref={glowB} className="thread-glint" d={THREAD} />
      <g ref={backN} className="needle">
        <Needle />
      </g>
      <g ref={letters}>
        <rect x="0" y="0" width="450" height="165" mask={`url(#${mask})`} className="letters" />
      </g>
      <g clipPath={`url(#${clip})`}>
        <path ref={frontT} className="thread" d={THREAD} />
        <path ref={glowF} className="thread-glint" d={THREAD} />
        <g ref={frontN} className="needle">
          <Needle />
        </g>
      </g>
    </svg>
  );
});

function Needle() {
  // tip at the right; the eye near the left end
  return (
    <g transform="scale(1.3)">
      <path d="M 86 0 L 14 -2.1 Q 0 -2.6 0 0 Q 0 2.6 14 2.1 Z" className="needle-body" />
      <ellipse cx="9" cy="0" rx="5" ry="0.85" className="needle-eye" />
    </g>
  );
}
