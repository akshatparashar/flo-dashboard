/* FLO colours, the same tokens as the web dashboard (frontend/src/styles/tokens.css): navy ink and blush from the
   logo, white sheets on a low-chroma navy frame, and hue only on data — blue for the main series, navy for the
   reference, red for what needs attention. */
import { useColorScheme } from "react-native";

export const light = {
  dark: false,
  frame: "#eef1f6",
  sheet: "#ffffff",
  sheetEdge: "#e3e7ee",
  well: "#f5f7fa",
  rule: "#edf0f4",
  ruleStrong: "#dce2ea",
  control: "#ffffff",
  controlEdge: "#d5dce6",
  pressed: "#f0f3f8",
  ink: "#0b1a33",
  ink2: "#44546c",
  muted: "#5f6e84",
  faint: "#93a0b3",
  brand: "#001938",
  onBrand: "#ffffff",
  accent: "#1f5fd1",
  accentSoft: "#e6eefc",
  seriesRef: "#0f2f6b",
  seriesPale: "#a8c1ee",
  seriesGrey: "#c3ccd8",
  neg: "#d22f3c",
  negSoft: "#fdebed",
  negInk: "#8f1a24",
  pos: "#18794a",
  posSoft: "#e3f4eb",
  posInk: "#0f5232",
  warn: "#a35f00",
  warnSoft: "#fdf1dd",
  warnInk: "#6d3f00",
  grid: "#e8ecf2",
  scrim: "rgba(11, 26, 51, 0.38)",
};

export type Palette = typeof light;

export const dark: Palette = {
  dark: true,
  frame: "#111a2b",
  sheet: "#18233a",
  sheetEdge: "#243150",
  well: "#1c2842",
  rule: "#223050",
  ruleStrong: "#2c3b5e",
  control: "#1c2842",
  controlEdge: "#33426a",
  pressed: "#213052",
  ink: "#eef1f7",
  ink2: "#b9c3d6",
  muted: "#95a2ba",
  faint: "#6d7a93",
  brand: "#fae8de",
  onBrand: "#1c2840",
  accent: "#6f9dff",
  accentSoft: "#233a68",
  seriesRef: "#dbe5fb",
  seriesPale: "#3f5d99",
  seriesGrey: "#4a5674",
  neg: "#ff6b75",
  negSoft: "rgba(255, 107, 117, 0.14)",
  negInk: "#ffb3b8",
  pos: "#4fc98a",
  posSoft: "rgba(79, 201, 138, 0.14)",
  posInk: "#9ae6bd",
  warn: "#f2b54d",
  warnSoft: "rgba(242, 181, 77, 0.14)",
  warnInk: "#f7d394",
  grid: "#24314f",
  scrim: "rgba(5, 10, 20, 0.6)",
};

export const font = {
  display: "BodoniModa_500Medium",
  displayBold: "BodoniModa_600SemiBold",
  ui: "InstrumentSans_400Regular",
  uiMedium: "InstrumentSans_500Medium",
  uiBold: "InstrumentSans_600SemiBold",
};

export function useTheme(): Palette {
  return useColorScheme() === "dark" ? dark : light;
}

/** Colour by meaning, never by position (same rules as the web charts). */
export function colorFor(name: string, i: number, c: Palette): string {
  const n = name.trim();
  if (/^(received|approved|achieved|new|rcvd|cumulative achieved|achieved \(new\)|on time)/i.test(n)) return c.accent;
  if (/^(pending|remaining|rejected|overdue|delayed|overdue \(pending\))/i.test(n)) return c.neg;
  if (/^(in production|under production|ordered|total|target|repeat|monthly target|cumulative target|fabric issue)/i.test(n))
    return c.seriesRef;
  if (/^(on hold|open|monthly incoming|in process)/i.test(n)) return c.seriesPale;
  if (/^(other|no date|cancelled)/i.test(n)) return c.seriesGrey;
  return [c.accent, c.seriesRef, c.seriesPale, c.seriesGrey][i % 4];
}
