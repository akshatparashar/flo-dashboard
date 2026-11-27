/* FLO World: the label hub, as on the web (/world). The live Dashboard card sits first; the 22 labels follow, each
   stitched to the one before it by a dashed thread, and open a "coming soon" room. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, type Href } from "expo-router";
import { useEffect, useState } from "react";
import { AccessibilityInfo, Animated, Easing, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { T } from "../../components/ui";
import { useStatus } from "../../lib/query";
import { font, useTheme } from "../../lib/theme";
import { DASHBOARD, LABELS } from "../../world/brands";
import { LogoMark, openPage, syncLine } from "../../world/parts";

const TYPED = "FLO intelligence online.";

export default function World() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const status = useStatus();
  const sync = syncLine(status.data);
  const [shown] = useState(() => new Animated.Value(0));
  const [typed, setTyped] = useState("");
  const cols = width >= 700 ? 4 : width >= 480 ? 3 : 2;
  const tile = (Math.min(width, 900) - 32 - (cols - 1) * 12) / cols;

  useEffect(() => {
    let alive = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (!alive) return;
      if (reduce) {
        shown.setValue(1);
        setTyped(TYPED);
        return;
      }
      Animated.timing(shown, { toValue: 1, duration: 1600, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
      let i = 0;
      const id = setInterval(() => {
        i++;
        setTyped(TYPED.slice(0, i));
        if (i >= TYPED.length) clearInterval(id);
      }, 45);
      return () => clearInterval(id);
    });
    return () => {
      alive = false;
    };
  }, [shown]);

  // labels come in one after another, from the dashboard outwards
  const appear = (i: number) => {
    const a = Math.min(0.9, 0.15 + i * 0.03);
    return {
      opacity: shown.interpolate({ inputRange: [0, a, Math.min(1, a + 0.12)], outputRange: [0, 0, 1], extrapolate: "clamp" }),
      transform: [{ scale: shown.interpolate({ inputRange: [0, a, Math.min(1, a + 0.12)], outputRange: [0.92, 0.92, 1], extrapolate: "clamp" }) }],
    };
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.frame }}>
      <View style={[st.head, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace("/welcome" as Href))} accessibilityRole="button" accessibilityLabel="Back to the FLO welcome screen" hitSlop={10} style={st.back}>
          <Ionicons name="arrow-back" size={22} color={c.ink} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={{ fontFamily: font.display, fontSize: 26, color: c.brand }} accessibilityRole="header">FLO World</Text>
          <Text style={{ fontFamily: font.uiMedium, fontSize: 12.5, color: c.muted, letterSpacing: 0.4 }}>{typed || " "}</Text>
        </View>
        <View style={st.back} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32 + insets.bottom, gap: 18, alignItems: "center" }}>
        <Animated.View style={[{ width: "100%", maxWidth: 868 }, appear(0)]}>
          <Pressable
            onPress={() => openPage("/")}
            accessibilityRole="link"
            accessibilityLabel="FLO Dashboard, live. Open it."
            style={({ pressed }) => [st.core, { backgroundColor: c.dark ? "#0b1424" : "#001938", opacity: pressed ? 0.9 : 1 }]}
          >
            <View style={st.live}>
              <View style={[st.dot, { backgroundColor: "#4fc98a" }]} />
              <Text style={{ fontFamily: font.uiBold, fontSize: 12, color: "#9ae6bd", letterSpacing: 1 }}>LIVE</Text>
            </View>
            <LogoMark label={DASHBOARD} width={Math.min(300, width * 0.62)} color="#fae8de" />
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: "#c9d2e3" }}>
                {sync ? `${sync.ok} of ${sync.total} sheets in sync · open the dashboard` : "Connecting to the sheets"}
              </Text>
              <Ionicons name="arrow-forward" size={15} color="#c9d2e3" />
            </View>
          </Pressable>
        </Animated.View>

        <View style={[st.grid, { maxWidth: 868 }]}>
          {LABELS.map((l, i) => (
            <Animated.View key={l.slug} style={[{ width: tile }, appear(i + 1)]}>
              {/* the dashed thread to the previous label in the row */}
              {i % cols !== 0 && <View style={[st.stitch, { borderColor: c.accent, left: -12, width: 12 }]} />}
              <Pressable
                onPress={() => router.push(`/world/${l.slug}` as Href)}
                accessibilityRole="link"
                accessibilityLabel={`FLO ${l.name}, coming soon`}
                style={({ pressed }) => [st.tile, { backgroundColor: c.sheet, borderColor: c.sheetEdge, opacity: pressed ? 0.8 : 1 }]}
              >
                <LogoMark label={l} width={tile - 32} />
                <Text style={{ fontFamily: font.uiMedium, fontSize: 11, color: c.faint, letterSpacing: 0.8 }}>COMING SOON</Text>
              </Pressable>
            </Animated.View>
          ))}
        </View>
        <T v="small">Choose a label to open it.</T>
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingBottom: 8 },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  core: { borderRadius: 24, paddingVertical: 28, paddingHorizontal: 20, alignItems: "center", gap: 16 },
  live: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" },
  dot: { width: 8, height: 8, borderRadius: 4 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12, width: "100%" },
  tile: { borderRadius: 16, borderWidth: StyleSheet.hairlineWidth, paddingVertical: 16, alignItems: "center", gap: 10 },
  stitch: { position: "absolute", top: "50%", borderTopWidth: 2, borderStyle: "dashed", opacity: 0.55 },
});
