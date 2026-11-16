/* Every dashboard screen: a scrolling page on the navy-tinted frame with a Bodoni title, one sentence that answers the
   page's question, and when the sheets were last read. Pull down to read the sheets again. While filters change, the
   old numbers stay (dimmed) until the new ones arrive. */
import type { UseQueryResult } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { clockIST } from "../lib/format";
import { useRefreshAll } from "../lib/query";
import { font, useTheme } from "../lib/theme";
import type { Envelope } from "../lib/types";
import { AssistantButton } from "./AssistantButton";
import { ErrorState, Skeleton, T } from "./ui";

export function Lede({ children }: { children: ReactNode }) {
  const c = useTheme();
  return <Text style={{ fontFamily: font.ui, fontSize: 17, lineHeight: 24, color: c.ink2 }}>{children}</Text>;
}

/** Bold figure inside a lede; `bad` makes it attention red. */
export function Em({ children, bad }: { children: ReactNode; bad?: boolean }) {
  const c = useTheme();
  return <Text style={{ fontFamily: font.uiBold, color: bad ? c.neg : c.ink }}>{children}</Text>;
}

function Stamp({ meta }: { meta: Envelope["meta"] }) {
  const c = useTheme();
  const color = meta.stale ? c.warn : c.pos;
  return (
    <View style={st.stamp}>
      <View style={[st.dot, { backgroundColor: color }]} />
      <T v="small" style={{ fontSize: 12.5 }}>
        {meta.stale ? "Delayed · showing the last good copy" : "Live"} · {meta.fy} · sheets read {clockIST(meta.synced_at)}
        {meta.source === "demo" ? " · demo data" : ""}
      </T>
    </View>
  );
}

export function Screen<T extends Envelope>({
  title,
  q,
  lede,
  filters,
  children,
  assistant = true,
  inStack = false,
}: {
  title: string;
  q: UseQueryResult<T, Error>;
  lede?: (d: T) => ReactNode;
  filters?: (d: T) => ReactNode;
  children: (d: T) => ReactNode;
  assistant?: boolean;
  /** opened from More, below a header with a back button: no status-bar inset needed */
  inStack?: boolean;
}) {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const refreshAll = useRefreshAll();
  const [pulling, setPulling] = useState(false);
  const d = q.data;

  const onRefresh = async () => {
    setPulling(true);
    try {
      await refreshAll();
    } finally {
      setPulling(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.frame }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: inStack ? 4 : insets.top + 12, paddingHorizontal: 16, paddingBottom: 120 + (inStack ? insets.bottom : 0) }}
        refreshControl={<RefreshControl refreshing={pulling} onRefresh={onRefresh} tintColor={c.muted} colors={[c.accent]} />}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[st.title, { color: c.brand }]} accessibilityRole="header">
          {title}
        </Text>
        {!d && q.isPending && <Skeleton />}
        {!d && q.error && <ErrorState message={q.error.message} onRetry={() => void q.refetch()} />}
        {d && (
          <View style={{ opacity: q.isPlaceholderData ? 0.55 : 1, gap: 14 }}>
            {lede && <Lede>{lede(d)}</Lede>}
            {d.meta && <Stamp meta={d.meta} />}
            {q.error && <T v="small" color={c.warn}>Couldn’t refresh just now ({q.error.message}). Showing the last numbers.</T>}
            {filters && <View style={{ gap: 10 }}>{filters(d)}</View>}
            <View>{children(d)}</View>
          </View>
        )}
      </ScrollView>
      {assistant && <AssistantButton bottom={inStack ? insets.bottom : 0} />}
    </View>
  );
}

const st = StyleSheet.create({
  title: { fontFamily: font.display, fontSize: 36, lineHeight: 42, letterSpacing: -0.4, marginBottom: 10 },
  stamp: { flexDirection: "row", alignItems: "center", gap: 7 },
  dot: { width: 7, height: 7, borderRadius: 4 },
});
