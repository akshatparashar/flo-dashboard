/* A label that is not built yet, as on the web (/world/:slug): its logo inside a slowly turning halo, a needle running
   a stitch line under it, and the way back. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { Redirect, router, useLocalSearchParams, type Href } from "expo-router";
import { useEffect, useState } from "react";
import { AccessibilityInfo, Animated, Easing, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Circle } from "react-native-svg";
import { T } from "../../components/ui";
import { font, useTheme } from "../../lib/theme";
import { labelBySlug } from "../../world/brands";
import { LogoMark, openPage } from "../../world/parts";

const STITCHES = 16;

export default function Soon() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const label = labelBySlug(slug);
  const [spin] = useState(() => new Animated.Value(0));
  const [sew] = useState(() => new Animated.Value(0));
  const [intro] = useState(() => new Animated.Value(0));

  useEffect(() => {
    let loops: Animated.CompositeAnimation[] = [];
    void AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (reduce) {
        intro.setValue(1);
        sew.setValue(1);
        return;
      }
      Animated.timing(intro, { toValue: 1, duration: 1300, easing: Easing.out(Easing.exp), useNativeDriver: true }).start();
      loops = [
        Animated.loop(Animated.timing(spin, { toValue: 1, duration: 40000, easing: Easing.linear, useNativeDriver: true })),
        Animated.loop(Animated.sequence([Animated.timing(sew, { toValue: 1, duration: 3400, easing: Easing.linear, useNativeDriver: true }), Animated.delay(900)])),
      ];
      loops.forEach((l) => l.start());
    });
    return () => loops.forEach((l) => l.stop());
  }, [spin, sew, intro]);

  if (!label) return <Redirect href={"/world" as Href} />;
  const W = 280;
  const step = W / STITCHES;

  return (
    <View style={{ flex: 1, backgroundColor: c.frame, paddingTop: insets.top + 8 }}>
      <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace("/world" as Href))} accessibilityRole="button" hitSlop={10} style={st.back}>
        <Ionicons name="arrow-back" size={20} color={c.ink} />
        <Text style={{ fontFamily: font.uiBold, fontSize: 15, color: c.ink }}>FLO World</Text>
      </Pressable>

      <View style={st.main}>
        <Animated.View style={[st.mark, { opacity: intro, transform: [{ scale: intro.interpolate({ inputRange: [0, 1], outputRange: [1.2, 1] }) }] }]}>
          <Animated.View style={[StyleSheet.absoluteFill, { transform: [{ rotate: spin.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] }) }] }]}>
            <Svg width="100%" height="100%" viewBox="0 0 200 200">
              <Circle cx={100} cy={100} r={96} fill="none" stroke={c.accent} strokeWidth={1.5} strokeDasharray="6 7" opacity={0.6} />
            </Svg>
          </Animated.View>
          <LogoMark label={label} width={170} />
        </Animated.View>

        {/* the stitch line sews itself under the logo, over and over */}
        <View style={{ width: W, height: 20, marginTop: 8 }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {Array.from({ length: STITCHES }, (_, i) => {
            const at = i / STITCHES;
            return (
              <Animated.View
                key={i}
                style={[st.st, { left: i * step + 3, width: step * 0.55, backgroundColor: c.ink2, opacity: sew.interpolate({ inputRange: [0, at, Math.min(1, at + 0.02), 1], outputRange: [0, 0, 1, 1] }) }]}
              />
            );
          })}
          <Animated.View style={[st.needle, { backgroundColor: c.ink2, transform: [{ translateX: sew.interpolate({ inputRange: [0, 1], outputRange: [-30, W + 10] }) }] }]} />
        </View>

        <Animated.View style={{ opacity: intro, gap: 12, alignItems: "center" }}>
          <Text style={[st.h1, { color: c.brand }]} accessibilityRole="header">FLO {label.name} is being stitched in.</Text>
          <T style={{ textAlign: "center", maxWidth: 380 }}>
            This label gets its own room in the FLO system soon. Until then, everything the house runs on lives in the FLO Dashboard.
          </T>
          <View style={{ gap: 10, marginTop: 8, alignItems: "center" }}>
            <Pressable onPress={() => openPage("/")} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: c.brand, opacity: pressed ? 0.85 : 1 }]}>
              <Text style={{ fontFamily: font.uiBold, fontSize: 15.5, color: c.onBrand }}>Open FLO Dashboard</Text>
              <Ionicons name="arrow-forward" size={17} color={c.onBrand} />
            </Pressable>
            <Pressable onPress={() => router.back()} accessibilityRole="button" style={({ pressed }) => [st.cta, { borderWidth: 1, borderColor: c.controlEdge, opacity: pressed ? 0.7 : 1 }]}>
              <Text style={{ fontFamily: font.uiBold, fontSize: 15.5, color: c.ink }}>Back to FLO World</Text>
            </Pressable>
          </View>
        </Animated.View>
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  back: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 16, paddingVertical: 8, alignSelf: "flex-start" },
  main: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 20, gap: 16, paddingBottom: 60 },
  mark: { width: 230, height: 230, alignItems: "center", justifyContent: "center" },
  st: { position: "absolute", top: 9, height: 2, borderRadius: 1 },
  needle: { position: "absolute", top: 8.5, width: 30, height: 3, borderTopRightRadius: 2, borderBottomRightRadius: 2 },
  h1: { fontFamily: font.display, fontSize: 30, lineHeight: 36, textAlign: "center", letterSpacing: -0.3 },
  cta: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 48, paddingHorizontal: 22, borderRadius: 999 },
});
