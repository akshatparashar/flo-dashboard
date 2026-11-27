/* Small pieces shared by the FLO World screens: a label's logo, the way into the dashboard, and the sheets' sync line. */
import { router, type Href } from "expo-router";
import { Image, type ImageStyle, type StyleProp } from "react-native";
import { ago } from "../lib/format";
import { useTheme } from "../lib/theme";
import type { StatusData } from "../lib/types";
import { LOGO_RATIO, markEntered, type Label } from "./brands";

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

const TABS = new Set(["/", "/production", "/fabric-po", "/target", "/more"]);

/** Leaves FLO World for a dashboard page: the tabs become the base of the stack, a page under More opens over them. */
export function openPage(to: string) {
  markEntered();
  if (router.canDismiss()) router.dismissAll();
  if (TABS.has(to)) {
    router.replace(to as Href);
    return;
  }
  router.replace("/");
  setTimeout(() => router.push(to as Href), 0);
}

export function syncLine(st: StatusData | undefined): { ok: number; total: number; when: string } | null {
  if (!st) return null;
  const all = Object.values(st.sources);
  const ok = all.filter((s) => s.ok).length;
  const latest = all.map((s) => s.synced_at).filter(Boolean).sort().pop() ?? null;
  return { ok, total: all.length, when: latest ? ago(latest) : "just now" };
}
