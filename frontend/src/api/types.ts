/* Shapes returned by the FLO API (backend/app). Shared later with the React Native app. */

export type Fmt = "text" | "int" | "dec" | "dec1" | "pct" | "inr" | "inr_full" | "date";
export type Tone = "good" | "alert";
export type NoticeKind = "info" | "success" | "warning" | "error";

export interface Kpi {
  id: string;
  label: string;
  value: number | string | null;
  unit: string;
  format: Fmt;
  hint?: string;
  tone?: Tone;
}

export interface Rate {
  good: number;
  mid: number;
}

export interface Column {
  key: string;
  label: string;
  format: Fmt;
  rate?: Rate;
}

export type Cell = number | string | boolean | null;

export interface TableData {
  title: string | null;
  note: string | null;
  columns: Column[];
  rows: Cell[][];
  meta: { kind: "total" | "ref" | null; muted: boolean }[];
  key_col: string | null;
  sorted: boolean;
}

export interface Series {
  name: string;
  values: number[];
  axis?: "left" | "right";
}

export interface SeriesChart {
  categories: string[];
  series: Series[];
}

export interface Slice {
  label: string;
  value: number;
}

export interface Notice {
  kind: NoticeKind;
  text: string;
}

export interface SourceMeta {
  source: string;
  synced_at: string | null;
  version: string;
  stale: boolean;
  error: string | null;
}

export interface Meta {
  fy: string;
  fy_months: string[];
  source: "google" | "demo";
  ttl: number;
  server_time: string;
  synced_at: string | null;
  version: string;
  stale: boolean;
  sources: SourceMeta[];
}

export interface Envelope {
  meta: Meta;
}

export type Options = Record<string, string[]>;

export interface DesignerData extends Envelope {
  options: Options;
  kpis: Kpi[];
  tables: { designers: TableData; categories: TableData };
  charts: { new_vs_repeat: SeriesChart; monthly_trend: SeriesChart };
}

export interface ClientData extends Envelope {
  options: Options;
  kpis: Kpi[];
  tables: { monthly: TableData; categories: TableData };
  charts: { monthly_share: Slice[]; fulfilment: Slice[]; category_by_month: SeriesChart };
}

export interface ProductionData extends Envelope {
  options: Options;
  kpis: Kpi[];
  tables: { categories: TableData; fabricators: TableData; monthly: TableData };
  charts: { by_category: SeriesChart; pending_share: Slice[]; monthly: SeriesChart };
  summary: { overdue_designs: number; pending_pct: number };
}

export interface SamplesData extends Envelope {
  empty?: boolean;
  options: Options;
  notices: Notice[];
  kpis: Kpi[];
  tables: { monthly: TableData; designers: TableData; vendors: TableData };
  charts: {
    monthly_status: SeriesChart;
    monthly_trend: SeriesChart;
    status_share: Slice[];
    designers: SeriesChart;
    vendors: SeriesChart;
  };
}

export interface FabricatorData extends Envelope {
  empty?: boolean;
  options: Options;
  metric: string;
  notices: Notice[];
  kpis: Kpi[];
  tables: { monthly: TableData; scorecard: TableData };
  check: Notice;
  matrix: null | {
    table: TableData;
    heatmap: { rows: string[]; columns: string[]; values: number[][] };
  };
  charts: {
    monthly: SeriesChart;
    issue_incoming: SeriesChart;
    rcvd_vs_remaining: SeriesChart;
    received_pct: Slice[];
  };
}

export interface FabricPoData extends Envelope {
  empty?: boolean;
  empty_filtered?: boolean;
  options: Options;
  rule: string;
  notices: Notice[];
  kpis: Kpi[];
  tables: { monthly: TableData; vendors: TableData; vendor_share: TableData; overdue: TableData; pos: TableData };
  overdue_total: number;
  charts: {
    monthly: SeriesChart;
    order_type: Slice[];
    vendors: SeriesChart;
    vendor_share: Slice[];
    timing: Slice[];
  };
}

export interface RepeatDesign {
  barcode: string;
  image: string;
  item: string;
  designer: string;
  orders: number;
  pcs: number;
  revenue: number;
  last: string;
}

export interface TargetData extends Envelope {
  empty?: boolean;
  options: Options;
  notices: Notice[];
  annual_target_cr: number;
  tracker: {
    kpis: Kpi[];
    gauge: { value: number; achieved: number; target: number };
    schedule: { gap: number; scheduled: number; elapsed: string[]; months_left: number };
    monthly: {
      categories: string[];
      achieved: number[];
      target: number[];
      cum_target: (number | null)[];
      cum_achieved: (number | null)[];
    };
    table: TableData;
    notices: Notice[];
  };
  quality: { notices: Notice[]; rows: TableData | null };
  filtered:
    | { empty: true; notices: Notice[] }
    | {
        empty?: false;
        kpis: Kpi[];
        tables: { monthly: TableData; designers: TableData; items: TableData; order_by: TableData; lines: TableData };
        lines_total: number;
        lines_truncated: boolean;
        top_repeat: RepeatDesign[];
        charts: { monthly: SeriesChart; designers: SeriesChart; items: Slice[]; order_by: Slice[] };
      };
}

export interface Alert {
  kind: NoticeKind;
  area: string;
  title: string;
  text: string;
  top?: { dimension: string; name: string; value: number }[];
}

export interface OverviewData extends Envelope {
  options: Options;
  alerts: Alert[];
  errors: Notice[];
  sections: {
    orders?: {
      kpis: Kpi[];
      stats: Record<string, number>;
      tables: { fabricators: TableData; categories: TableData; clients: TableData };
      charts: { monthly: SeriesChart; fabricators: SeriesChart };
    };
    stock?: { kpis: Kpi[]; table: TableData; chart: SeriesChart };
    po?: {
      kpis: Kpi[];
      tables: { vendors: TableData; overdue: TableData };
      overdue_total: number;
      timing: Slice[];
    };
    samples?: { kpis: Kpi[]; table: TableData; chart: SeriesChart };
    designers?: { table: TableData };
  };
}

export interface SourceStatus {
  name: string;
  ok: boolean;
  error: string | null;
  stale: boolean;
  synced_at: string | null;
  version: string;
  tabs: string[];
}

export interface StatusData {
  source: "google" | "demo";
  ttl: number;
  fy: string;
  server_time: string;
  sources: Record<string, SourceStatus>;
}

export interface Health {
  ok: boolean;
  version: string;
  source: "google" | "demo";
  ttl: number;
  auth_required: boolean;
}
