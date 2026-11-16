import { useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";
const KEY = "flo-theme";

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function resolvedTheme(): "light" | "dark" {
  const attr = document.documentElement.dataset.theme;
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(read);
  const [resolved, setResolved] = useState<"light" | "dark">(() => (typeof document !== "undefined" ? resolvedTheme() : "light"));
  useEffect(() => {
    const root = document.documentElement;
    if (pref === "system") delete root.dataset.theme;
    else root.dataset.theme = pref;
    try {
      if (pref === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, pref);
    } catch {
      /* ignore */
    }
    setResolved(resolvedTheme());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setResolved(resolvedTheme());
    mq.addEventListener("change", on);
    const meta = document.querySelectorAll('meta[name="theme-color"]');
    meta.forEach((m) => m.setAttribute("content", resolvedTheme() === "dark" ? "#111a2b" : "#eef1f6"));
    return () => mq.removeEventListener("change", on);
  }, [pref]);
  const toggle = () => setPref(resolved === "dark" ? "light" : "dark");
  return { pref, resolved, setPref, toggle };
}
