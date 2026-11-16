/* Filters for a phone: months as a row of chips under the title (the filter used most), everything else (designer,
   vendor, client…) in a sheet behind one "Filters" button that shows how many are on. Leaving a filter empty
   means "all", exactly like the web dashboard and the API. */
import { useCallback, useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { shortMonth, titleCase } from "../lib/format";
import { font, useTheme } from "../lib/theme";
import type { Options } from "../lib/types";
import { Button, T } from "./ui";

export type FilterValues = Record<string, string[]>;

export function useFilters(keys: string[]) {
  const [values, setValues] = useState<FilterValues>(() => Object.fromEntries(keys.map((k) => [k, []])));
  const set = useCallback((k: string, v: string[]) => setValues((s) => ({ ...s, [k]: v })), []);
  const reset = useCallback(() => setValues(Object.fromEntries(keys.map((k) => [k, []]))), [keys]);
  const active = Object.values(values).filter((v) => v.length).length;
  return { values, set, reset, setAll: setValues, active };
}

function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: on }}
      style={({ pressed }) => [
        st.chip,
        { backgroundColor: on ? c.brand : c.control, borderColor: on ? c.brand : c.controlEdge, opacity: pressed ? 0.8 : 1 },
      ]}
    >
      <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: on ? c.onBrand : c.ink }}>{label}</Text>
    </Pressable>
  );
}

export function MonthChips({ months, value, onChange }: { months: string[]; value: string[]; onChange: (v: string[]) => void }) {
  if (!months?.length) return null;
  const toggle = (m: string) => onChange(value.includes(m) ? value.filter((x) => x !== m) : months.filter((x) => x === m || value.includes(x)));
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: 16 }} style={{ marginHorizontal: -16 }}>
      <Chip label="All months" on={!value.length} onPress={() => onChange([])} />
      {months.map((m) => (
        <Chip key={m} label={shortMonth(m)} on={value.includes(m)} onPress={() => toggle(m)} />
      ))}
    </ScrollView>
  );
}

export interface FilterGroup {
  key: string;
  label: string;
  single?: boolean;
  /** keep the sheet's spelling (statuses like "PARTIAL RCVD") instead of title case */
  raw?: boolean;
}

export function FilterButton({ groups, options, values, onApply }: { groups: FilterGroup[]; options: Options; values: FilterValues; onApply: (v: FilterValues) => void }) {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<FilterValues>(values);
  const usable = useMemo(() => groups.filter((g) => (options[g.key] ?? []).length > 0), [groups, options]);
  const count = usable.filter((g) => values[g.key]?.length).length;
  if (!usable.length) return null;

  const show = () => {
    setDraft(values);
    setOpen(true);
  };
  const toggle = (g: FilterGroup, v: string) =>
    setDraft((d) => {
      const cur = d[g.key] ?? [];
      const next = cur.includes(v) ? cur.filter((x) => x !== v) : g.single ? [v] : [...cur, v];
      return { ...d, [g.key]: next };
    });

  return (
    <>
      <Pressable
        onPress={show}
        accessibilityRole="button"
        accessibilityLabel={count ? `Filters, ${count} on` : "Filters"}
        style={({ pressed }) => [st.fbtn, { backgroundColor: count ? c.accentSoft : c.control, borderColor: count ? c.accent : c.controlEdge, opacity: pressed ? 0.8 : 1 }]}
      >
        <Text style={{ fontFamily: font.uiBold, fontSize: 14, color: c.ink }}>Filters</Text>
        {count > 0 && (
          <View style={[st.badge, { backgroundColor: c.accent }]}>
            <Text style={{ color: "#fff", fontFamily: font.uiBold, fontSize: 12 }}>{count}</Text>
          </View>
        )}
      </Pressable>
      <Modal visible={open} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setOpen(false)} transparent={false}>
        <View style={{ flex: 1, backgroundColor: c.frame, paddingTop: 8 }}>
          <View style={st.sheetHead}>
            <Text style={{ fontFamily: font.display, fontSize: 26, color: c.brand, flex: 1 }}>Filters</Text>
            <Pressable onPress={() => setDraft(Object.fromEntries(usable.map((g) => [g.key, []])))} hitSlop={10} accessibilityRole="button">
              <Text style={{ fontFamily: font.uiBold, fontSize: 15, color: c.accent }}>Clear all</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: 16, gap: 22, paddingBottom: 24 }}>
            {usable.map((g) => (
              <View key={g.key} style={{ gap: 10 }}>
                <T v="title">
                  {g.label}
                  <Text style={{ fontFamily: font.ui, color: c.muted, fontSize: 13 }}>{draft[g.key]?.length ? `  ·  ${draft[g.key].length} chosen` : "  ·  all"}</Text>
                </T>
                <View style={st.wrap}>
                  {options[g.key].map((v) => (
                    <Chip key={v} label={g.raw ? v : titleCase(v)} on={(draft[g.key] ?? []).includes(v)} onPress={() => toggle(g, v)} />
                  ))}
                </View>
              </View>
            ))}
          </ScrollView>
          <View style={[st.sheetFoot, { borderColor: c.rule, backgroundColor: c.sheet, paddingBottom: 12 + insets.bottom }]}>
            <View style={{ flex: 1 }}>
              <Button label="Cancel" onPress={() => setOpen(false)} />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                label="Show results"
                kind="primary"
                onPress={() => {
                  onApply({ ...values, ...draft });
                  setOpen(false);
                }}
              />
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const st = StyleSheet.create({
  chip: { paddingHorizontal: 13, minHeight: 36, justifyContent: "center", borderRadius: 999, borderWidth: 1 },
  fbtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, minHeight: 36, borderRadius: 999, borderWidth: 1 },
  badge: { minWidth: 20, height: 20, borderRadius: 10, alignItems: "center", justifyContent: "center", paddingHorizontal: 5 },
  sheetHead: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  sheetFoot: { flexDirection: "row", gap: 10, paddingHorizontal: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth },
});
