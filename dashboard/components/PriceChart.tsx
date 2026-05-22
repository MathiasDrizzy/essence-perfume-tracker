"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { formatCLP, retailerColor, retailerLabel } from "@/lib/utils";

type HistRow = { retailer: string; scraped_at: string; price_clp: number };

export default function PriceChart({ history }: { history: HistRow[] }) {
  const retailers = Array.from(new Set(history.map((h) => h.retailer)));
  const byDate = new Map<string, Record<string, number | string>>();
  for (const row of history) {
    const day = row.scraped_at.slice(0, 10);
    if (!byDate.has(day)) byDate.set(day, { date: day });
    byDate.get(day)![row.retailer] = row.price_clp;
  }
  const data = Array.from(byDate.values()).sort((a, b) =>
    String(a.date).localeCompare(String(b.date)),
  );

  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={data} margin={{ top: 16, right: 30, bottom: 8, left: 10 }}>
        <CartesianGrid stroke="rgb(var(--rule))" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "rgb(var(--muted))" }}
          tickFormatter={(d: string) => {
            const [, m, day] = d.split("-");
            return `${day}/${m}`;
          }}
          stroke="rgb(var(--rule))"
        />
        <YAxis
          tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "rgb(var(--muted))" }}
          tickFormatter={(v) => (typeof v === "number" ? `${(v / 1000).toFixed(0)}k` : v)}
          stroke="rgb(var(--rule))"
          width={48}
        />
        <Tooltip
          formatter={(v: number, name: string) => [formatCLP(v), retailerLabel(name)]}
          labelFormatter={(label: string) =>
            new Date(label).toLocaleDateString("es-CL", {
              day: "2-digit",
              month: "long",
              year: "numeric",
            })
          }
          contentStyle={{
            background: "rgb(var(--bone))",
            border: "1px solid rgb(var(--ink))",
            borderRadius: 0,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            padding: "10px 14px",
          }}
          labelStyle={{ color: "rgb(var(--ink))", fontSize: 10, marginBottom: 4 }}
          itemStyle={{ color: "rgb(var(--ink))" }}
        />
        <Legend
          wrapperStyle={{ fontSize: 10, fontFamily: "JetBrains Mono", paddingTop: 12 }}
          iconType="plainline"
          iconSize={20}
          formatter={(value: string) => (
            <span style={{ color: "rgb(var(--ink-soft))", letterSpacing: "0.08em" }}>
              {retailerLabel(value).toUpperCase()}
            </span>
          )}
        />
        {retailers.map((r) => (
          <Line
            key={r}
            type="monotone"
            dataKey={r}
            stroke={retailerColor(r)}
            strokeWidth={1.6}
            dot={{ r: 2.5, strokeWidth: 0, fill: retailerColor(r) }}
            activeDot={{ r: 4, strokeWidth: 1.5, stroke: "rgb(var(--bone))" }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
