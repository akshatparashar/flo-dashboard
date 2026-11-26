import type { CSSProperties } from "react";
import { logoUrl, type Label } from "./brands";

/** One FLO label logo, recoloured by theme: the transparent artwork is a mask filled with currentColor. */
export function LogoMark({ label, width, className = "", style, decorative = false }: { label: Label; width?: number | string; className?: string; style?: CSSProperties; decorative?: boolean }) {
  const url = `url(${logoUrl(label.slug)})`;
  return (
    <span
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : `FLO ${label.name}`}
      aria-hidden={decorative || undefined}
      className={`logo-mark ${className}`}
      style={{
        width,
        aspectRatio: String(label.ratio),
        WebkitMaskImage: url,
        maskImage: url,
        ...style,
      }}
    />
  );
}
