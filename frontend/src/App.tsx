import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, getToken, setToken } from "./api/client";
import { useHealth, useStatus } from "./api/hooks";
import { Assistant } from "./components/assistant/Assistant";
import { Wordmark } from "./components/Brand";
import { Preloader } from "./components/Preloader";
import { Shell } from "./components/shell/Shell";
import { PageSkeleton } from "./components/ui";
import Overview from "./pages/Overview";

const Production = lazy(() => import("./pages/Production"));
const Designers = lazy(() => import("./pages/Designers"));
const Clients = lazy(() => import("./pages/Clients"));
const Samples = lazy(() => import("./pages/Samples"));
const Fabricators = lazy(() => import("./pages/Fabricators"));
const FabricPO = lazy(() => import("./pages/FabricPO"));
const Target = lazy(() => import("./pages/Target"));
const FloFuture = lazy(() => import("./pages/FloFuture"));
const VendorRate = lazy(() => import("./pages/VendorRate"));
const InOutSale = lazy(() => import("./pages/InOutSale"));

function SignIn({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await api<{ token: string }>("/auth/login", undefined, { method: "POST", body: JSON.stringify({ passcode: code }) });
      setToken(r.token);
      onDone();
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="signin">
      <form onSubmit={submit}>
        <Wordmark variant="letters" height={30} />
        <h1>Operations dashboard</h1>
        <p>Enter the team passcode to see live production, orders and revenue.</p>
        <input className="field" type="password" autoComplete="current-password" placeholder="Passcode" value={code} onChange={(e) => setCode(e.target.value)} autoFocus aria-label="Passcode" />
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn primary" type="submit" disabled={busy || !code}>
          {busy ? "Checking…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

/** The intro plays on the first visit of a browser session; ?nointro skips it (automated checks). */
function introWanted(): boolean {
  try {
    if (new URLSearchParams(window.location.search).has("nointro")) return false;
    return sessionStorage.getItem("flo-intro") !== "1";
  } catch {
    return true;
  }
}

function Dashboard() {
  const status = useStatus();
  const [loading, setLoading] = useState(introWanted);
  const finish = () => {
    try {
      sessionStorage.setItem("flo-intro", "1");
    } catch {
      /* ignore */
    }
    setLoading(false);
  };
  return (
    <>
      <Shell>
        <Suspense fallback={<div className="page"><PageSkeleton /></div>}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/production" element={<Production />} />
            <Route path="/designers" element={<Designers />} />
            <Route path="/clients" element={<Clients />} />
            <Route path="/samples" element={<Samples />} />
            <Route path="/fabricators" element={<Fabricators />} />
            <Route path="/fabric-po" element={<FabricPO />} />
            <Route path="/target" element={<Target />} />
            <Route path="/flo-future" element={<FloFuture />} />
            <Route path="/vendor-rate" element={<VendorRate />} />
            <Route path="/in-out-sale" element={<InOutSale />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
      <Assistant />
      {loading &&<Preloader status={status.data ?? (status.error ? ({ sources: {} } as never) : undefined)} onDone={finish} />}
    </>
  );
}

export default function App() {
  const health = useHealth();
  const [signedIn, setSignedIn] = useState(() => !!getToken());
  useEffect(() => {
    const out = () => {
      setToken(null);
      setSignedIn(false);
    };
    window.addEventListener("flo:signed-out", out);
    return () => window.removeEventListener("flo:signed-out", out);
  }, []);
  if (health.data?.auth_required && !signedIn) return <SignIn onDone={() => setSignedIn(true)} />;
  return <Dashboard />;
}
