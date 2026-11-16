/* App root: fonts, data and sign-in providers, and the navigation stack. Until the owner signs in only the sign-in
   screen exists; afterwards the dashboard tabs, the detail pages and FLO Assistant. */
import { BodoniModa_500Medium } from "@expo-google-fonts/bodoni-moda/500Medium";
import { BodoniModa_600SemiBold } from "@expo-google-fonts/bodoni-moda/600SemiBold";
import { InstrumentSans_400Regular } from "@expo-google-fonts/instrument-sans/400Regular";
import { InstrumentSans_500Medium } from "@expo-google-fonts/instrument-sans/500Medium";
import { InstrumentSans_600SemiBold } from "@expo-google-fonts/instrument-sans/600SemiBold";
import { QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../lib/auth";
import { queryClient, useAppFocus } from "../lib/query";
import { useTheme } from "../lib/theme";

void SplashScreen.preventAutoHideAsync().catch(() => {});

function Navigation({ fontsReady }: { fontsReady: boolean }) {
  const { ready, signedIn } = useAuth();
  const c = useTheme();
  useAppFocus();
  const show = ready && fontsReady;
  useEffect(() => {
    if (show) void SplashScreen.hideAsync().catch(() => {});
  }, [show]);
  if (!show) return null;

  const nav = c.dark ? DarkTheme : DefaultTheme;
  const theme = { ...nav, colors: { ...nav.colors, background: c.frame, card: c.sheet, text: c.ink, border: c.rule, primary: c.accent } };
  const detail = {
    headerShown: true,
    headerTitle: "",
    headerBackTitle: "More",
    headerShadowVisible: false,
    headerStyle: { backgroundColor: c.frame },
    headerTintColor: c.ink,
  } as const;

  return (
    <ThemeProvider value={theme}>
      <StatusBar style={c.dark ? "light" : "dark"} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.frame } }}>
        <Stack.Protected guard={signedIn}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="designers" options={detail} />
          <Stack.Screen name="clients" options={detail} />
          <Stack.Screen name="samples" options={detail} />
          <Stack.Screen name="fabricators" options={detail} />
          <Stack.Screen name="assistant" options={{ presentation: "modal", contentStyle: { backgroundColor: c.sheet } }} />
        </Stack.Protected>
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="sign-in" />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}

export default function RootLayout() {
  const [loaded, error] = useFonts({
    BodoniModa_500Medium,
    BodoniModa_600SemiBold,
    InstrumentSans_400Regular,
    InstrumentSans_500Medium,
    InstrumentSans_600SemiBold,
  });
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          {/* if a font fails to load the app still opens, in the system font */}
          <Navigation fontsReady={loaded || !!error} />
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
