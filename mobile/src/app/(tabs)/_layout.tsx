/* Bottom tabs for the four screens the owner opens most; the rest live under More. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { Tabs } from "expo-router/js-tabs";
import type { ComponentProps } from "react";
import type { ColorValue } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { font, useTheme } from "../../lib/theme";

type Icon = ComponentProps<typeof Ionicons>["name"];

function icon(on: Icon, off: Icon) {
  return function TabIcon({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) {
    return <Ionicons name={focused ? on : off} color={color as string} size={size - 2} />;
  };
}

export default function TabsLayout() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: c.brand,
        tabBarInactiveTintColor: c.muted,
        tabBarLabelStyle: { fontFamily: font.uiMedium, fontSize: 11.5, lineHeight: 14 },
        tabBarStyle: { backgroundColor: c.sheet, borderTopColor: c.sheetEdge, height: 64 + insets.bottom, paddingTop: 4, paddingBottom: insets.bottom + 6 },
        sceneStyle: { backgroundColor: c.frame },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Overview", tabBarIcon: icon("home", "home-outline") }} />
      <Tabs.Screen name="production" options={{ title: "Production", tabBarIcon: icon("cube", "cube-outline") }} />
      <Tabs.Screen name="fabric-po" options={{ title: "Fabric PO", tabBarIcon: icon("layers", "layers-outline") }} />
      <Tabs.Screen name="target" options={{ title: "Revenue", tabBarIcon: icon("trending-up", "trending-up-outline") }} />
      <Tabs.Screen name="more" options={{ title: "More", tabBarIcon: icon("grid", "grid-outline") }} />
    </Tabs>
  );
}
