/* FLO Assistant on the phone: the same POST /api/chat as the web widget, so it answers from the dashboard's own
   numbers (read-only), in English or Hinglish, and keeps the subject for follow-ups ("and for May?"). The chat
   lasts for as long as the app is open. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, type Href } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type ScrollViewInstance } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RichText } from "../components/RichText";
import { Robot } from "../components/Robot";
import { T } from "../components/ui";
import { api } from "../lib/api";
import { font, useTheme } from "../lib/theme";

type Reply = { answer: string; page: string | null; page_label: string | null; context: Record<string, unknown>; understood: boolean };
type Msg = { id: number; role: "user" | "bot"; text: string; page?: string | null; pageLabel?: string | null; error?: boolean; retry?: string };

const MAX_LEN = 500;
const WELCOME = "Hi! I'm **FLO Assistant**. Ask me anything about the dashboard: any number, name or month, in English or Hinglish.";
const SUGGESTIONS = ["Total pending", "This month revenue", "Overdue POs", "Top 3 vendors by pending fabric", "Sabse zyada pending kis fabricator ke paas hai", "New vs repeat revenue"];

// kept outside the component so closing and reopening the chat keeps the conversation
const memory: { msgs: Msg[]; ctx: Record<string, unknown> | null; next: number } = { msgs: [], ctx: null, next: 1 };
const remember = (patch: Partial<typeof memory>) => Object.assign(memory, patch);
const nextId = () => memory.next++;

/** Web paths in answers -> app screens (they are the same names). */
const ROUTES = new Set(["/", "/production", "/fabric-po", "/target", "/designers", "/clients", "/samples", "/fabricators"]);

/** Android draws edge to edge, so the window no longer shrinks for the keyboard: track its height ourselves.
    React Native reports it without the navigation bar, which insets.bottom already covers. */
function useAndroidKeyboard(): number {
  const [h, setH] = useState(0);
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const show = Keyboard.addListener("keyboardDidShow", (e) => setH(e.endCoordinates.height));
    const hide = Keyboard.addListener("keyboardDidHide", () => setH(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return h;
}

export default function Assistant() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const [msgs, setMsgs] = useState<Msg[]>(memory.msgs);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<ScrollViewInstance>(null);
  const keyboard = useAndroidKeyboard();

  useEffect(() => {
    remember({ msgs });
    const t = setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(t);
  }, [msgs, busy, keyboard]);

  const push = (m: Omit<Msg, "id">) => setMsgs((s) => [...s, { ...m, id: nextId() }]);

  const send = async (text: string) => {
    const message = text.trim().slice(0, MAX_LEN);
    if (!message || busy) return;
    push({ role: "user", text: message });
    setDraft("");
    setBusy(true);
    try {
      const r = await api<Reply>("/chat", undefined, { method: "POST", body: { message, context: memory.ctx }, timeoutMs: 60_000 });
      if (r.understood) remember({ ctx: r.context });
      push({ role: "bot", text: r.answer, page: r.page, pageLabel: r.page_label });
    } catch (e) {
      push({ role: "bot", text: (e as Error).message || "Something went wrong. Please try again.", error: true, retry: message });
    } finally {
      setBusy(false);
    }
  };

  const retry = (m: Msg) => {
    setMsgs((s) => {
      const i = s.findIndex((x) => x.id === m.id);
      const from = i > 0 && s[i - 1].role === "user" ? i - 1 : i;
      return [...s.slice(0, from), ...s.slice(i + 1)];
    });
    if (m.retry) void send(m.retry);
  };

  const reset = () => {
    remember({ ctx: null });
    setMsgs([]);
  };

  /** Closes the chat, then shows the page the answer came from (a tab, or a page under More). */
  const open = (page: string) => {
    router.back();
    router.navigate(page as Href);
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.sheet }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={[st.head, { paddingTop: Platform.OS === "ios" ? 14 : insets.top + 10, borderColor: c.rule }]}>
        <View style={[st.avatar, { backgroundColor: c.brand }]}>
          <Robot size={24} color={c.onBrand} />
        </View>
        <View style={{ flex: 1 }}>
          <T v="title">FLO Assistant</T>
          <T v="small" style={{ fontSize: 12.5 }}>Answers from this dashboard · read-only</T>
        </View>
        <Pressable onPress={reset} disabled={!msgs.length || busy} hitSlop={8} accessibilityRole="button" accessibilityLabel="Start a new chat" style={{ opacity: !msgs.length || busy ? 0.35 : 1, padding: 6 }}>
          <Ionicons name="refresh" size={21} color={c.ink} />
        </Pressable>
        <Pressable onPress={() => router.back()} hitSlop={8} accessibilityRole="button" accessibilityLabel="Close FLO Assistant" style={{ padding: 6 }}>
          <Ionicons name="close" size={24} color={c.ink} />
        </Pressable>
      </View>

      <ScrollView ref={listRef} style={{ flex: 1, backgroundColor: c.frame }} contentContainerStyle={{ padding: 16, gap: 10 }} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive">
        <View style={[st.bubble, st.bot, { backgroundColor: c.sheet, borderColor: c.sheetEdge }]}>
          <RichText text={WELCOME} color={c.ink2} strong={c.ink} />
        </View>
        {!msgs.length && (
          <View style={{ gap: 8, marginTop: 4 }}>
            <T v="label">Try asking</T>
            <View style={st.suggest}>
              {SUGGESTIONS.map((s) => (
                <Pressable key={s} onPress={() => void send(s)} accessibilityRole="button" style={({ pressed }) => [st.chip, { borderColor: c.controlEdge, backgroundColor: pressed ? c.pressed : c.control }]}>
                  <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: c.ink }}>{s}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}
        {msgs.map((m) =>
          m.role === "user" ? (
            <View key={m.id} style={[st.bubble, st.user, { backgroundColor: c.brand }]}>
              <Text style={{ fontFamily: font.ui, fontSize: 15, lineHeight: 21, color: c.onBrand }} selectable>
                {m.text}
              </Text>
            </View>
          ) : (
            <View key={m.id} style={[st.bubble, st.bot, { backgroundColor: m.error ? c.negSoft : c.sheet, borderColor: m.error ? "transparent" : c.sheetEdge }]}>
              <RichText text={m.text} color={m.error ? c.negInk : c.ink2} strong={m.error ? c.negInk : c.ink} />
              {m.page && ROUTES.has(m.page) && (
                <Pressable onPress={() => open(m.page!)} hitSlop={6} accessibilityRole="link">
                  <Text style={{ fontFamily: font.uiBold, fontSize: 13.5, color: c.accent, marginTop: 4 }}>Open {m.pageLabel ?? "page"} →</Text>
                </Pressable>
              )}
              {m.error && m.retry && (
                <Pressable onPress={() => retry(m)} disabled={busy} accessibilityRole="button" style={[st.retry, { borderColor: c.negInk }]}>
                  <Text style={{ fontFamily: font.uiBold, fontSize: 13.5, color: c.negInk }}>Try again</Text>
                </Pressable>
              )}
            </View>
          ),
        )}
        {busy && (
          <View style={[st.bubble, st.bot, { backgroundColor: c.sheet, borderColor: c.sheetEdge, flexDirection: "row", alignItems: "center", gap: 8 }]} accessibilityLabel="FLO Assistant is typing">
            <ActivityIndicator size="small" color={c.muted} />
            <T v="small">Reading the dashboard…</T>
          </View>
        )}
      </ScrollView>

      <View style={[st.input, { borderColor: c.rule, backgroundColor: c.sheet, paddingBottom: 10 + insets.bottom + keyboard }]}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Ask about the dashboard…"
          placeholderTextColor={c.faint}
          maxLength={MAX_LEN}
          multiline
          style={[st.field, { backgroundColor: c.control, borderColor: c.controlEdge, color: c.ink }]}
          accessibilityLabel="Your question"
          submitBehavior="submit"
          returnKeyType="send"
          onSubmitEditing={() => void send(draft)}
        />
        <Pressable
          onPress={() => void send(draft)}
          disabled={!draft.trim() || busy}
          accessibilityRole="button"
          accessibilityLabel="Send"
          style={[st.send, { backgroundColor: c.brand, opacity: !draft.trim() || busy ? 0.35 : 1 }]}
        >
          <Ionicons name="arrow-up" size={20} color={c.onBrand} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  avatar: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  bubble: { maxWidth: "88%", borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10, gap: 4 },
  bot: { alignSelf: "flex-start", borderWidth: StyleSheet.hairlineWidth, borderTopLeftRadius: 4 },
  user: { alignSelf: "flex-end", borderTopRightRadius: 4 },
  suggest: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 },
  retry: { alignSelf: "flex-start", borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6, marginTop: 6 },
  input: { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 12, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth },
  field: { flex: 1, minHeight: 44, maxHeight: 120, borderWidth: 1, borderRadius: 14, paddingHorizontal: 14, paddingTop: 11, paddingBottom: 11, fontSize: 16, fontFamily: font.ui },
  send: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
});
