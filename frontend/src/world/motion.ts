import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";

gsap.registerPlugin(useGSAP, ScrollTrigger, MotionPathPlugin, SplitText, ScrambleTextPlugin);

export { gsap, ScrollTrigger, SplitText, useGSAP };

export function reduced(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Spring-like ease used for arrivals across FLO World (fast out, long settle). */
export const ARRIVE = "expo.out";
export const SETTLE = "power3.inOut";
