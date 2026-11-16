/* Who is signed in, and to which server. The token and address live in the phone's secure storage, so the owner
   signs in once per phone (tokens last as long as the server allows, 14 days by default). */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, configureApi, DEFAULT_SERVER, normalizeServer, onSignedOut } from "./api";
import { getItem, setItem } from "./storage";
import type { Health } from "./types";

const SERVER_KEY = "flo.server";
const TOKEN_KEY = "flo.token";

interface AuthState {
  ready: boolean;
  server: string;
  signedIn: boolean;
  /** Checks the server, then signs in with the passcode (or without one when the server asks for none). */
  signIn: (server: string, passcode: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [server, setServer] = useState(DEFAULT_SERVER);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const [savedServer, savedToken] = await Promise.all([getItem(SERVER_KEY), getItem(TOKEN_KEY)]);
      if (!alive) return;
      const s = savedServer || DEFAULT_SERVER;
      configureApi({ server: s, token: savedToken });
      setServer(s);
      // "signed in" = we hold a token, or a server that needs no passcode was confirmed earlier
      setSignedIn(!!s && savedToken !== null);
      setReady(true);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const signOut = useCallback(async () => {
    configureApi({ token: null });
    setSignedIn(false);
    await setItem(TOKEN_KEY, null);
  }, []);

  useEffect(() => onSignedOut(() => void signOut()), [signOut]);

  const signIn = useCallback(async (rawServer: string, passcode: string) => {
    const s = normalizeServer(rawServer);
    if (!s) throw new Error("Enter the dashboard address.");
    const health = await api<Health>("/health", undefined, { server: s, timeoutMs: 20_000 });
    if (!health || health.ok !== true) throw new Error("That address is not a FLO dashboard.");
    let token = "";
    if (health.auth_required) {
      if (!passcode) throw new Error("Enter the team passcode.");
      configureApi({ server: s, token: null });
      const r = await api<{ token: string }>("/auth/login", undefined, { method: "POST", body: { passcode }, timeoutMs: 20_000 });
      token = r.token;
    }
    configureApi({ server: s, token: token || null });
    await Promise.all([setItem(SERVER_KEY, s), setItem(TOKEN_KEY, token)]);
    setServer(s);
    setSignedIn(true);
  }, []);

  const value = useMemo(() => ({ ready, server, signedIn, signIn, signOut }), [ready, server, signedIn, signIn, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
