import { Building2, ClipboardCheck, Factory, IndianRupee, LayoutDashboard, Menu, Moon, Package, Palette, PanelLeftClose, PanelLeftOpen, RefreshCw, Scissors, Shirt, Sun, Target, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useFetchingReporter, useRefreshAll } from "../../api/hooks";
import { useLive } from "../../lib/live";
import { useTheme } from "../../lib/theme";
import { Wordmark } from "../Brand";
import { LiveStatus } from "./LiveStatus";

export const NAV = [
  { group: "Operations", items: [
    { to: "/", label: "Overview", icon: LayoutDashboard },
    { to: "/production", label: "Production", icon: Factory },
    { to: "/fabricators", label: "Fabricators", icon: Scissors },
    { to: "/fabric-po", label: "Fabric PO", icon: Package },
    { to: "/vendor-rate", label: "Vendor Rate", icon: IndianRupee },
  ] },
  { group: "Design and sales", items: [
    { to: "/designers", label: "Designers", icon: Palette },
    { to: "/clients", label: "Clients Order Status", icon: Building2 },
    { to: "/samples", label: "Samples", icon: Shirt },
    { to: "/target", label: "Designer Order Target", icon: Target },
    { to: "/flo-future", label: "FLO Future", icon: ClipboardCheck },
  ] },
];

export function pageLabel(path: string) {
  for (const g of NAV) for (const it of g.items) if (it.to === path) return it.label;
  return "Overview";
}

const NAV_KEY = "flo-nav";

/** Desktop: the sidebar can fold into an icon rail. Remembered per device. */
export function navCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_KEY) === "rail";
  } catch {
    return false;
  }
}

export function Shell({ children }: { children: ReactNode }) {
  useFetchingReporter();
  const { resolved, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const [rail, setRail] = useState(navCollapsed);
  const toggleRail = () =>
    setRail((r) => {
      try {
        localStorage.setItem(NAV_KEY, r ? "full" : "rail");
      } catch {
        /* ignore */
      }
      return !r;
    });
  useEffect(() => {
    // "[" folds or unfolds the sidebar, unless the person is typing
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key !== "[" || e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable) return;
      e.preventDefault();
      toggleRail();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const [spinning, setSpinning] = useState(false);
  const loc = useLocation();
  const live = useLive();
  const refresh = useRefreshAll();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    document.title = `${pageLabel(loc.pathname)} · FLO Operations`;
  }, [loc.pathname]);

  const doRefresh = async () => {
    setSpinning(true);
    await refresh();
    setTimeout(() => setSpinning(false), 500);
  };

  return (
    <div className={`app${open ? " nav-open" : ""}${rail ? " nav-rail" : ""}`}>
      <aside className="sidebar" aria-label="Main navigation">
        <NavLink to="/" className="brand" aria-label="FLO Operations home">
          <Wordmark variant="letters" height={rail ? 15 : 22} />
          <span className="brand-scope">
            Operations
            <br />
            {live.meta?.fy ?? "FY 2026-27"}
          </span>
        </NavLink>
        <nav className="nav">
          {NAV.map((g) => (
            <div key={g.group} style={{ display: "contents" }}>
              <div className="nav-group">{g.group}</div>
              {g.items.map((it) => (
                <NavLink key={it.to} to={{ pathname: it.to }} end={it.to === "/"} title={rail ? it.label : undefined}>
                  <it.icon aria-hidden="true" />
                  <span className="label">{it.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="stamp" style={{ padding: "0 8px", whiteSpace: "normal" }}>
            Read-only view of the FLO Google Sheets. Edit data in the sheets; it shows here within a minute.
          </div>
        </div>
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <header className="topbar">
        <button className="btn ghost icon menu-btn" onClick={() => setOpen(!open)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
          {open ? <X /> : <Menu />}
        </button>
        <button className="btn ghost icon rail-btn" onClick={toggleRail} aria-label={rail ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!rail} title={`${rail ? "Expand" : "Collapse"} sidebar  [`}>
          {rail ? <PanelLeftOpen /> : <PanelLeftClose />}
        </button>
        <div className="crumb">
          <span className="scope">FLO · </span>
          <b>{pageLabel(loc.pathname)}</b>
        </div>
        <div className="topbar-right">
          {live.meta?.source === "demo" && (
            <span className="demo-chip" title="No Google key is configured, so built-in sample data is shown.">
              Demo data
            </span>
          )}
          <LiveStatus />
          <button className="btn ghost icon refresh" onClick={doRefresh} aria-label="Read the sheets again now" title="Read the sheets again now">
            <RefreshCw style={{ transition: "transform 500ms var(--ease-out)", transform: spinning ? "rotate(360deg)" : "none" }} />
          </button>
          <button className="btn ghost icon" onClick={toggle} aria-label={resolved === "dark" ? "Switch to light mode" : "Switch to dark mode"} title={resolved === "dark" ? "Light mode" : "Dark mode"}>
            {resolved === "dark" ? <Sun /> : <Moon />}
          </button>
        </div>
      </header>
      <main className="sheet" id="main">
        {children}
      </main>
    </div>
  );
}
