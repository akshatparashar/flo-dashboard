/* More: the other dashboards, FLO Assistant, the state of each Google Sheet, and sign out. */
import Ionicons from "@expo/vector-icons/Ionicons";
import Constants from "expo-constants";
import { router, type Href } from "expo-router";
import type { ComponentProps, ReactNode } from "react";
import { useState } from "react";
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Robot } from "../../components/Robot";
import { Button, Card, T } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { ago } from "../../lib/format";
import { useRefreshAll, useStatus } from "../../lib/query";
import { font, useTheme } from "../../lib/theme";

type Icon = ComponentProps<typeof Ionicons>["name"];

const PAGES: { to: Href; title: string; sub: string; icon: Icon }[] = [
  { to: "/designers", title: "Designers", sub: "New and repeat pcs per designer", icon: "color-palette-outline" },
  { to: "/clients", title: "Clients", sub: "Orders and fulfilment per client", icon: "people-outline" },
  { to: "/samples", title: "Samples", sub: "Approved, rejected and in process", icon: "shirt-outline" },
  { to: "/fabricators", title: "Fabricators", sub: "Stock with each fabricator, month by month", icon: "construct-outline" },
];

function Row({ title, sub, onPress, left, first }: { title: string; sub?: string; onPress: () => void; left: ReactNode; first?: boolean }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="link" accessibilityLabel={sub ? `${title}. ${sub}` : title} style={({ pressed }) => [st.row, { backgroundColor: pressed ? c.pressed : "transparent", borderColor: c.rule, borderTopWidth: first ? 0 : StyleSheet.hairlineWidth }]}>
      <View style={[st.icon, { backgroundColor: c.well }]}>{left}</View>
      <View style={{ flex: 1 }}>
        <T v="title">{title}</T>
        {sub && <T v="small">{sub}</T>}
      </View>
      <Ionicons name="chevron-forward" size={18} color={c.faint} />
    </Pressable>
  );
}

export default function More() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const auth = useAuth();
  const status = useStatus();
  const refreshAll = useRefreshAll();
  const [reading, setReading] = useState(false);

  const signOut = () => {
    if (Platform.OS === "web") return void auth.signOut();
    Alert.alert("Sign out?", "You'll need the team passcode to sign in again.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: () => void auth.signOut() },
    ]);
  };

  const readNow = async () => {
    setReading(true);
    try {
      await refreshAll();
    } finally {
      setReading(false);
    }
  };

  const sources = status.data ? Object.values(status.data.sources) : [];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: c.frame }} contentContainerStyle={{ paddingTop: insets.top + 12, paddingHorizontal: 16, paddingBottom: 40, gap: 20 }}>
      <Text style={[st.title, { color: c.brand }]} accessibilityRole="header">
        More
      </Text>

      <Card flush>
        {PAGES.map((p, i) => (
          <Row key={p.title} first={i === 0} title={p.title} sub={p.sub} onPress={() => router.push(p.to)} left={<Ionicons name={p.icon} size={20} color={c.ink} />} />
        ))}
        <Row title="FLO Assistant" sub="Ask about any number, in English or Hinglish" onPress={() => router.push("/assistant")} left={<Robot size={22} color={c.ink} />} />
      </Card>

      <View style={{ gap: 10 }}>
        <Text style={{ fontFamily: font.display, fontSize: 22, color: c.brand }}>Google Sheets</Text>
        <Card style={{ gap: 12 }}>
          {status.isPending && <T v="small">Checking the sheets…</T>}
          {status.error && <T v="small" color={c.neg}>{status.error.message}</T>}
          {sources.map((s) => (
            <View key={s.name} style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={[st.dot, { backgroundColor: !s.ok ? c.neg : s.stale ? c.warn : c.pos }]} />
              <View style={{ flex: 1 }}>
                <T v="strong" style={{ fontSize: 14 }}>{s.name}</T>
                <T v="small" style={{ fontSize: 12.5 }}>{s.ok ? `Read ${ago(s.synced_at)}${s.stale ? " · delayed" : ""}` : s.error ?? "Can't be read right now"}</T>
              </View>
            </View>
          ))}
          {status.data?.source === "demo" && <T v="small">The server is showing demo data, not the real sheets.</T>}
          <Button label={reading ? "Reading the sheets…" : "Read the sheets now"} onPress={readNow} disabled={reading} />
          <T v="small" style={{ fontSize: 12.5 }}>The app also reads them by itself every minute, and when you pull down on any page.</T>
        </Card>
      </View>

      <View style={{ gap: 10 }}>
        <Text style={{ fontFamily: font.display, fontSize: 22, color: c.brand }}>Account</Text>
        <Card style={{ gap: 12 }}>
          <View>
            <T v="label">Dashboard</T>
            <T v="strong" style={{ fontSize: 14 }} selectable>{auth.server.replace(/^https?:\/\//, "")}</T>
          </View>
          <Button label="Sign out" onPress={signOut} />
        </Card>
        <T v="small" style={{ textAlign: "center" }}>
          FLO Operations · version {Constants.expoConfig?.version ?? "1.0.0"} · read-only
        </T>
      </View>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  title: { fontFamily: font.display, fontSize: 36, lineHeight: 42, letterSpacing: -0.4 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 14 },
  icon: { width: 38, height: 38, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  dot: { width: 9, height: 9, borderRadius: 5 },
});
