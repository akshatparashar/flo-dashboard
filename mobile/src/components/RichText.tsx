/* Renders the assistant's plain-text answers: **bold**, line breaks, "• " bullets and "1. " numbered lines (same
   rules as the web widget). Only Text elements are built, so an answer can never inject anything. */
import { Fragment, type ReactNode } from "react";
import { Text, View } from "react-native";
import { font } from "../lib/theme";

function inline(text: string, color: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <Text key={i} style={{ fontFamily: font.uiBold, color }}>
        {part.slice(2, -2)}
      </Text>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function RichText({ text, color, strong }: { text: string; color: string; strong: string }) {
  const base = { fontFamily: font.ui, fontSize: 15, lineHeight: 21, color };
  const out: ReactNode[] = [];
  text.split("\n").forEach((line, i) => {
    const bullet = line.match(/^\s*•\s+(.*)$/);
    const num = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (bullet || num) {
      out.push(
        <View key={i} style={{ flexDirection: "row", gap: 6, paddingLeft: 2 }}>
          <Text style={[base, { minWidth: num ? 18 : 10 }]}>{num ? `${num[1]}.` : "•"}</Text>
          <Text style={[base, { flex: 1 }]}>{inline(bullet ? bullet[1] : num![2], strong)}</Text>
        </View>,
      );
    } else if (line.trim()) {
      out.push(
        <Text key={i} style={base}>
          {inline(line, strong)}
        </Text>,
      );
    }
  });
  return <View style={{ gap: 4 }}>{out}</View>;
}
