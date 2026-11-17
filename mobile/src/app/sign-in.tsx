/* Sign in once per phone: the dashboard address (pre-filled when the app was built with EXPO_PUBLIC_API_URL) and the
   team passcode, the same one as on the web dashboard. */
import { useState } from "react";
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button, T } from "../components/ui";
import { DEFAULT_SERVER } from "../lib/api";
import { useAuth } from "../lib/auth";
import { font, useTheme } from "../lib/theme";

export default function SignIn() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const auth = useAuth();
  const [server, setServer] = useState(auth.server || DEFAULT_SERVER);
  const [showServer, setShowServer] = useState(!DEFAULT_SERVER);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await auth.signIn(server, code);
    } catch (e) {
      setErr((e as Error).message || "Couldn't sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const input = [st.input, { backgroundColor: c.control, borderColor: c.controlEdge, color: c.ink }];

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.frame }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={[st.wrap, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled">
        <Image
          source={c.dark ? require("../../assets/brand/flo-wordmark-blush.png") : require("../../assets/brand/flo-wordmark-navy.png")}
          style={{ width: 150, height: 106, alignSelf: "center" }}
          resizeMode="contain"
          accessibilityLabel="FLO, Fashion Lifestyle Outfit"
        />
        <View style={[st.card, { backgroundColor: c.sheet, borderColor: c.sheetEdge }]}>
          <Text style={{ fontFamily: font.display, fontSize: 28, lineHeight: 34, color: c.brand }}>Operations dashboard</Text>
          <T>Live production, orders, fabric, samples and revenue, straight from the team’s Google Sheets.</T>

          {showServer ? (
            <View style={{ gap: 6 }}>
              <T v="label">Dashboard address</T>
              <TextInput
                value={server}
                onChangeText={setServer}
                placeholder="flo-dashboardd.vercel.app"
                placeholderTextColor={c.faint}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                textContentType="URL"
                style={input}
                accessibilityLabel="Dashboard address"
              />
            </View>
          ) : null}

          <View style={{ gap: 6 }}>
            <T v="label">Team passcode</T>
            <TextInput
              value={code}
              onChangeText={setCode}
              placeholder="Passcode"
              placeholderTextColor={c.faint}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={submit}
              style={input}
              accessibilityLabel="Team passcode"
            />
            <T v="small">Leave it empty if your dashboard doesn’t use a passcode.</T>
          </View>

          {err && (
            <View style={[st.err, { backgroundColor: c.negSoft }]} accessibilityLiveRegion="polite">
              <T v="small" color={c.negInk}>{err}</T>
            </View>
          )}

          <Button label={busy ? "Checking…" : "Sign in"} kind="primary" onPress={submit} disabled={busy || !server.trim()} />

          {!showServer && (
            <Pressable onPress={() => setShowServer(true)} hitSlop={8} accessibilityRole="button" style={{ alignSelf: "center" }}>
              <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: c.muted }}>Use a different dashboard address</Text>
            </Pressable>
          )}
        </View>
        <T v="small" style={{ textAlign: "center" }}>Read-only: the app can never change a sheet.</T>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  wrap: { paddingHorizontal: 20, gap: 24, flexGrow: 1, justifyContent: "center", maxWidth: 480, width: "100%", alignSelf: "center" },
  card: { borderRadius: 20, borderWidth: StyleSheet.hairlineWidth, padding: 20, gap: 16 },
  input: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, minHeight: 48, fontSize: 16, fontFamily: font.ui },
  err: { borderRadius: 10, padding: 10 },
});
