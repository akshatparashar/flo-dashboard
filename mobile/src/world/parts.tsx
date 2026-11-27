/* Small pieces shared by the FLO World screens: a label's logo, the way into the dashboard, and the sheets' sync line. */
import { router, type Href } from "expo-router";
import { Image, type ImageStyle, type StyleProp } from "react-native";
import { ago } from "../lib/format";
import { useTheme } from "../lib/theme";
import type { StatusData } from "../lib/types";
import { LOGO_RATIO, type Label } from "./brands";

export function LogoMark({ label, width, color, style }: { label: Label; width: number; color?: string; style?: StyleProp<ImageStyle> }) {
  const c = useTheme();
  return (
    <Image
      source={label.logo}
      accessibilityLabel={`FLO ${label.name}`}
      style={[{ width, height: width / LOGO_RATIO, tintColor: color ?? c.brand }, style]}
      resizeMode="contain"
    />
  );
}

const TABS = new Set(["/overview", "/production", "/fabric-po", "/target", "/more"]);

/** Leaves the landing screen or FLO World for a dashboard page: the tabs open over the landing screen (back returns
 *  there), and a page under More opens over the tabs. */
export function openPage(to: string) {
  if (router.canDismiss()) router.dismissAll();
  if (TABS.has(to)) {
    router.push(to as Href);
    return;
  }
  router.push("/overview" as Href);
  setTimeout(() => router.push(to as Href), 0);
}

export function syncLine(st: StatusData | undefined): { ok: number; total: number; when: string } | null {
  if (!st) return null;
  const all = Object.values(st.sources);
  const ok = all.filter((s) => s.ok).length;
  const latest = all.map((s) => s.synced_at).filter(Boolean).sort().pop() ?? null;
  return { ok, total: all.length, when: latest ? ago(latest) : "just now" };
}
