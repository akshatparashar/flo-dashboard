/* Overview: what needs attention right now, across every sheet. */
import { router, type Href } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Bars, Split, StackedList } from "../../components/charts";
import { DataTable } from "../../components/DataTable";
import { MonthChips, useFilters } from "../../components/Filters";
import { Em, Screen } from "../../components/Screen";
import { KpiGrid, Notices, Panel, Section, T } from "../../components/ui";
import { useDashboard } from "../../lib/query";
import { font, useTheme } from "../../lib/theme";
import type { Alert, OverviewData } from "../../lib/types";

const KEYS = ["month"];
const AREA_LINK: Record<string, Href> = { orders: "/production", overdue: "/production", stock: "/fabricators", po: "/fabric-po", samples: "/samples" };
const AREA_NAME: Record<string, string> = { orders: "Production", overdue: "Delivery", stock: "Fabricator stock", po: "Fabric PO", samples: "Samples", none: "Data" };
const SEVERITY: Record<string, number> = { error: 0, warning: 1, info: 2, success: 3 };

function AlertCard({ a }: { a: Alert }) {
  const c = useTheme();
  const tone = { error: c.neg, warning: c.warn, info: c.accent, success: c.pos }[a.kind];
  const to = AREA_LINK[a.area];
  return (
    <Pressable
      onPress={to ? () => router.push(to) : undefined}
      disabled={!to}
      accessibilityRole={to ? "link" : undefined}
      style={({ pressed }) => [st.alert, { backgroundColor: c.sheet, borderColor: c.sheetEdge, borderLeftColor: tone, opacity: pressed ? 0.85 : 1 }]}
    >
      <Text style={{ fontFamily: font.uiBold, fontSize: 11.5, letterSpacing: 0.6, color: tone, textTransform: "uppercase" }}>{AREA_NAME[a.area] ?? a.area}</Text>
      <T v="title">{a.title}</T>
      <T v="small" style={{ color: c.ink2 }}>{a.text}</T>
      {a.top?.map((t) => (
        <T key={t.dimension} v="small">
          Most pending {t.dimension.toLowerCase()}: <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{t.name}</Text> ({t.value.toLocaleString("en-US")})
        </T>
      ))}
      {to && <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.accent }}>Open {AREA_NAME[a.area]} →</Text>}
    </Pressable>
  );
}

function Open({ to, label }: { to: Href; label: string }) {
  const c = useTheme();
  return (
    <Pressable onPress={() => router.push(to)} hitSlop={8} accessibilityRole="link">
      <Text style={{ fontFamily: font.uiBold, fontSize: 13.5, color: c.accent }}>{label} →</Text>
    </Pressable>
  );
}

export default function Overview() {
  const f = useFilters(KEYS);
  const q = useDashboard<OverviewData>("/overview", { month: f.values.month });
  return (
    <Screen
      title="Overview"
      q={q}
      lede={(d) => {
        const worst = [...d.alerts].filter((a) => a.kind === "error" || a.kind === "warning").sort((a, b) => SEVERITY[a.kind] - SEVERITY[b.kind]);
        if (!worst.length) return "Nothing needs attention right now.";
        return (
          <>
            <Em bad>{worst[0].title}</Em>
            {worst[1] ? <> and <Em>{worst[1].title}</Em></> : null} need attention{f.values.month.length ? " in the selected months" : " this year"}.
          </>
        );
      }}
      filters={(d) => <MonthChips months={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />}
    >
      {(d) => {
        const s = d.sections;
        const alerts = [...d.alerts].sort((a, b) => SEVERITY[a.kind] - SEVERITY[b.kind]);
        return (
          <>
            <Notices items={d.errors} />
            {alerts.length > 0 && (
              <View style={{ gap: 10, marginTop: 4 }}>
                {alerts.map((a) => (
                  <AlertCard key={a.area + a.title} a={a} />
                ))}
              </View>
            )}

            {s.orders && (
              <Section title="Orders and production" sub="Master sheet, by order month" action={<Open to="/production" label="Production" />}>
                <KpiGrid kpis={s.orders.kpis.filter((k) => k.id !== "designs")} lead={["pending"]} />
                <Panel title="Received and pending by month" sub="Pcs · tap a month for figures">
                  <Bars data={s.orders.charts.monthly} stacked unit="pcs" />
                </Panel>
                <Panel title="Pending by fabricator" sub="Pcs, most pending first">
                  <StackedList data={s.orders.charts.fabricators} unit="pcs" sortBy="Pending" />
                </Panel>
                <Panel title="Pending and overdue by fabricator" flush>
                  <DataTable table={s.orders.tables.fabricators} name="overview_orders_fabricators" maxRows={8} />
                </Panel>
                <Panel title="Pending by client" flush>
                  <DataTable table={s.orders.tables.clients} name="overview_orders_clients" maxRows={8} />
                </Panel>
              </Section>
            )}

            {s.po && (
              <Section title="Fabric POs" sub="Fabric ordering and receiving" action={<Open to="/fabric-po" label="Fabric PO" />}>
                <KpiGrid kpis={s.po.kpis} lead={["overdue"]} />
                <Panel title="Delivery status" sub="Count of POs">
                  <Split items={s.po.timing} unit="POs" />
                </Panel>
                <Panel title="Overdue POs, not yet received" sub={s.po.overdue_total > 15 ? `Oldest 15 of ${s.po.overdue_total}` : `${s.po.overdue_total} POs`} flush>
                  {s.po.overdue_total ? (
                    <DataTable table={s.po.tables.overdue} name="overview_po_overdue" maxRows={8} titleCaseFirst={false} />
                  ) : (
                    <T style={{ padding: 16 }}>No PO is overdue.</T>
                  )}
                </Panel>
              </Section>
            )}

            {s.stock && (
              <Section title="Fabricator stock" sub="Fabricator report" action={<Open to="/fabricators" label="Fabricators" />}>
                <KpiGrid kpis={s.stock.kpis} lead={["remaining"]} />
                <Panel title="Stock by fabricator" flush>
                  <DataTable table={s.stock.table} name="overview_stock" />
                </Panel>
              </Section>
            )}

            {s.samples && (
              <Section title="Samples" sub="Sample summary, by process date" action={<Open to="/samples" label="Samples" />}>
                <KpiGrid kpis={s.samples.kpis} lead={["approval_pct"]} />
                <Panel title="Sample status by month" sub="Pcs · tap a month for figures">
                  <Bars data={s.samples.chart} stacked unit="pcs" />
                </Panel>
              </Section>
            )}

            {s.designers && (
              <Section title="Designers" sub="Orders with samples" action={<Open to="/designers" label="Designers" />}>
                <Panel flush>
                  <DataTable table={s.designers.table} name="overview_designers" maxRows={10} />
                </Panel>
              </Section>
            )}
          </>
        );
      }}
    </Screen>
  );
}

const st = StyleSheet.create({
  alert: { borderRadius: 14, borderWidth: StyleSheet.hairlineWidth, borderLeftWidth: 4, padding: 14, gap: 4 },
});
