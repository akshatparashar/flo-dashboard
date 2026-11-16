/* The FLO logo, recoloured by theme: the transparent navy artwork is used as a mask and filled with --brand
   (navy on light, blush on dark), so the exact letterforms of the logo are kept. */

const SRC = {
  letters: { url: "/brand/flo-letters-navy.png", ratio: 450 / 165 },
  full: { url: "/brand/flo-wordmark-navy.png", ratio: 800 / 566 },
};

export function Wordmark({ variant = "letters", height = 24, className = "", style }: { variant?: "letters" | "full"; height?: number; className?: string; style?: React.CSSProperties }) {
  const s = SRC[variant];
  return (
    <span
      role="img"
      aria-label="FLO"
      className={className}
      style={{
        display: "inline-block",
        height,
        width: height * s.ratio,
        background: "var(--brand)",
        WebkitMaskImage: `url(${s.url})`,
        maskImage: `url(${s.url})`,
        WebkitMaskSize: "contain",
        maskSize: "contain",
        WebkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        maskPosition: "center",
        flex: "none",
        ...style,
      }}
    />
  );
}

/** The logo's open bracket in its own 1600 x 1131 artwork space: top-right end, top-right corner, top-left corner,
 *  bottom-left corner, bottom end. Stroke 9. */
export const BRACKET = [
  [1474, 264],
  [1474, 136],
  [125, 136],
  [125, 956],
  [295, 956],
] as const;
export const ART = { w: 1600, h: 1131, stroke: 9 };
