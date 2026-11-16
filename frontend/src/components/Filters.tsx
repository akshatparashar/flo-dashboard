import { Calendar, Check, ChevronDown, RotateCcw } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { describeMonths, monthRange } from "../lib/filters";
import { shortMonth, titleCase } from "../lib/format";

function usePopover() {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  useLayoutEffect(() => {
    if (!open || !btn.current) return;
    const r = btn.current.getBoundingClientRect();
    const w = Math.min(320, window.innerWidth - 24);
    setPos({ top: r.bottom + 6, left: Math.max(12, Math.min(r.left, window.innerWidth - w - 12)) });
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!pop.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btn.current?.focus();
      }
    };
    const onScroll = (e: Event) => {
      if (!pop.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", () => setOpen(false), { once: true });
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);
  return { open, setOpen, btn, pop, pos };
}

function Trigger({ label, value, isSet, open, onClick, btnRef, icon, controls }: { label: string; value: string; isSet: boolean; open: boolean; onClick: () => void; btnRef: React.RefObject<HTMLButtonElement | null>; icon?: ReactNode; controls: string }) {
  return (
    <button ref={btnRef} type="button" className={`fbtn${isSet ? " is-set" : ""}`} aria-haspopup="dialog" aria-expanded={open} aria-controls={controls} onClick={onClick}>
      {icon}
      <span className="k">{label}</span>
      <span className="v">{value}</span>
      <ChevronDown aria-hidden="true" />
    </button>
  );
}

interface MultiProps {
  label: string;
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  pretty?: (s: string) => string;
  single?: boolean;
  allLabel?: string;
}

export function MultiSelect({ label, options, value, onChange, pretty = titleCase, single = false, allLabel = "All" }: MultiProps) {
  const { open, setOpen, btn, pop, pos } = usePopover();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const id = useId();
  const list = useMemo(() => options.filter((o) => pretty(o).toLowerCase().includes(q.trim().toLowerCase())), [options, q, pretty]);
  useEffect(() => {
    if (!open) setQ("");
    setActive(0);
  }, [open]);

  const toggle = (o: string) => {
    if (single) {
      onChange(value[0] === o ? [] : [o]);
      setOpen(false);
      return;
    }
    onChange(value.includes(o) ? value.filter((v) => v !== o) : [...value, o]);
  };
  const shown = !value.length ? allLabel : value.length === 1 ? pretty(value[0]) : `${value.length} selected`;

  return (
    <>
      <Trigger label={label} value={shown} isSet={value.length > 0} open={open} onClick={() => setOpen(!open)} btnRef={btn} controls={id} />
      {open &&
        createPortal(
          <div className="popover" ref={pop} id={id} role="dialog" aria-label={`Filter by ${label}`} style={{ top: pos.top, left: pos.left }}>
            {options.length > 7 && (
              <div className="popover-head">
                <input
                  type="search"
                  autoFocus
                  placeholder={`Search ${label.toLowerCase()}`}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") setActive((a) => Math.min(list.length - 1, a + 1));
                    if (e.key === "ArrowUp") setActive((a) => Math.max(0, a - 1));
                    if (e.key === "Enter" && list[active]) toggle(list[active]);
                  }}
                />
              </div>
            )}
            <div className="opt-list" role="listbox" aria-multiselectable={!single}>
              {list.map((o, i) => (
                <button type="button" key={o} className={`opt${i === active ? " is-active" : ""}`} role="option" aria-checked={value.includes(o)} aria-selected={value.includes(o)} onClick={() => toggle(o)} onMouseEnter={() => setActive(i)}>
                  <span className="check">{value.includes(o) && <Check />}</span>
                  {pretty(o)}
                </button>
              ))}
              {!list.length && <div className="state">No match for “{q}”.</div>}
            </div>
            <div className="popover-foot">
              <span>{value.length ? `${value.length} of ${options.length} selected` : `Showing all ${options.length}`}</span>
              <button type="button" className="btn ghost sm" onClick={() => onChange([])} disabled={!value.length}>
                Clear
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

type Mode = "all" | "range" | "pick";

export function MonthFilter({ label = "Month", options, value, onChange }: { label?: string; options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const { open, setOpen, btn, pop, pos } = usePopover();
  const id = useId();
  const dated = options.filter((o) => /^[A-Za-z]+-\d{2}$/.test(o));
  const initialMode: Mode = !value.length ? "all" : monthRange(dated, value[0], value[value.length - 1]).length === value.length ? "range" : "pick";
  const [mode, setMode] = useState<Mode>(initialMode);
  const [from, setFrom] = useState(value[0] ?? dated[0] ?? "");
  const [to, setTo] = useState(value[value.length - 1] ?? dated[dated.length - 1] ?? "");
  useEffect(() => {
    if (open) {
      setMode(initialMode);
      setFrom(value[0] ?? dated[0] ?? "");
      setTo(value[value.length - 1] ?? dated[dated.length - 1] ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const applyRange = (f: string, t: string) => {
    setFrom(f);
    setTo(t);
    onChange(monthRange(dated, f, t));
  };

  return (
    <>
      <Trigger label={label} value={describeMonths(value, options, shortMonth)} isSet={value.length > 0} open={open} onClick={() => setOpen(!open)} btnRef={btn} icon={<Calendar aria-hidden="true" />} controls={id} />
      {open &&
        createPortal(
          <div className="popover" ref={pop} id={id} role="dialog" aria-label={`Filter by ${label}`} style={{ top: pos.top, left: pos.left }}>
            <div className="popover-head">
              <div className="seg" role="group" aria-label="Month filter type">
                {(["all", "range", "pick"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    aria-pressed={mode === m}
                    onClick={() => {
                      setMode(m);
                      if (m === "all") onChange([]);
                      if (m === "range") applyRange(from || dated[0], to || dated[dated.length - 1]);
                    }}
                  >
                    {m === "all" ? "All months" : m === "range" ? "Range" : "Pick months"}
                  </button>
                ))}
              </div>
              {mode === "range" && (
                <div className="range-row">
                  <label>
                    From
                    <select className="field" value={from} onChange={(e) => applyRange(e.target.value, to)}>
                      {dated.map((m) => (
                        <option key={m} value={m}>
                          {shortMonth(m)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    To
                    <select className="field" value={to} onChange={(e) => applyRange(from, e.target.value)}>
                      {dated.map((m) => (
                        <option key={m} value={m}>
                          {shortMonth(m)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </div>
            {mode === "pick" && (
              <div className="opt-list" role="listbox" aria-multiselectable="true">
                {options.map((o) => (
                  <button type="button" key={o} className="opt" role="option" aria-checked={value.includes(o)} aria-selected={value.includes(o)} onClick={() => onChange(value.includes(o) ? value.filter((v) => v !== o) : options.filter((x) => x === o || value.includes(x)))}>
                    <span className="check">{value.includes(o) && <Check />}</span>
                    {shortMonth(o)}
                  </button>
                ))}
              </div>
            )}
            <div className="popover-foot">
              <span>{mode === "all" ? "Every month is included." : value.length ? `${value.length} month${value.length > 1 ? "s" : ""} selected` : "Nothing picked = all months"}</span>
              <button type="button" className="btn ghost sm" onClick={() => setOpen(false)}>
                Done
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

export function FilterBar({ children, active, onReset, right }: { children: ReactNode; active: number; onReset: () => void; right?: ReactNode }) {
  return (
    <div className="filters" role="toolbar" aria-label="Filters">
      {children}
      {active > 0 && (
        <button type="button" className="btn ghost sm" onClick={onReset}>
          <RotateCcw /> Reset
        </button>
      )}
      <span className="spacer" />
      {right}
    </div>
  );
}
