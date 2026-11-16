/* The round robot button in the corner of every dashboard screen; opens FLO Assistant. */
import { router } from "expo-router";
import { Pressable, StyleSheet } from "react-native";
import { useTheme } from "../lib/theme";
import { Robot } from "./Robot";

export function AssistantButton({ bottom = 0 }: { bottom?: number }) {
  const c = useTheme();
  return (
    <Pressable
      onPress={() => router.push("/assistant")}
      accessibilityRole="button"
      accessibilityLabel="Ask FLO Assistant"
      style={({ pressed }) => [
        st.fab,
        { bottom: 16 + bottom, backgroundColor: c.brand, transform: [{ scale: pressed ? 0.94 : 1 }], shadowColor: "#0b1a33" },
      ]}
    >
      <Robot size={30} color={c.onBrand} />
    </Pressable>
  );
}

const st = StyleSheet.create({
  fab: {
    position: "absolute",
    right: 16,
    bottom: 16,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    elevation: 6,
    shadowOpacity: 0.25,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
  },
});
