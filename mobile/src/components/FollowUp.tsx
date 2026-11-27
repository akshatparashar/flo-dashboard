/* Promised samples to chase: overdue first (red edge), then due in the next three days (amber edge). */
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { fmtInt } from "../lib/format";
import { font, useTheme } from "../lib/theme";
import type { PromiseItem } from "../lib/types";
import { T } from "./ui";

export function FollowUp({ items, empty, max = 8 }: { items: PromiseItem[]; empty: string; max?: number }) {
  const c = useTheme();
  const [all, setAll] = useState(false);
  if (!items.length) return <T style={{ padding: 16 }}>{empty}</T>;
  const shown = all ? items : items.slice(0, max);
  return (
    <View>
      {shown.map((a, i) => (
        <View key={`${a.designer}-${a.item}-${i}`} style={[st.row, { borderColor: c.rule, borderLeftColor: a.level === "error" ? c.neg : c.warn, borderTopWidth: i ? StyleSheet.hairlineWidth : 0 }]}>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <T v="strong" style={{ flex: 1, fontSize: 14.5 }} numberOfLines={2}>{a.item}</T>
            <Text style={{ fontFamily: font.uiBold, fontSize: 12.5, color: a.level === "error" ? c.neg : c.warnInk }}>{a.reason}</Text>
          </View>
          <T v="small">
            {a.designer}
            {a.team && !a.team.startsWith("(") ? ` · ${a.team}` : ""}
            {a.vendor ? ` · ${a.vendor}` : ""} · {a.status}
          </T>
          <T v="small" style={{ color: c.ink, fontVariant: ["tabular-nums"] }}>
            {fmtInt(a.pending)} pcs pending{a.due ? ` · due ${a.due}` : ""}
          </T>
        </View>
      ))}
      {items.length > max && (
        <Pressable onPress={() => setAll((x) => !x)} hitSlop={8} accessibilityRole="button" style={{ padding: 16 }}>
          <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.accent }}>{all ? "Show fewer" : `Show all ${items.length}`}</Text>
        </Pressable>
      )}
    </View>
  );
}

const st = StyleSheet.create({
  row: { borderLeftWidth: 4, paddingHorizontal: 14, paddingVertical: 12, gap: 3 },
});
