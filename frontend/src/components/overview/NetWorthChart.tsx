import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatMoney, type NetWorthHistoryReport } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  data: NetWorthHistoryReport;
  currentNetWorth: string;
};

function formatAxis(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}k`;
  return `$${value}`;
}

function formatTooltipDate(date: string) {
  const d = new Date(date + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export default function NetWorthChart({ data, currentNetWorth }: Props) {
  const chartData = data.points.map((p) => ({
    date: p.date,
    netWorth: Number(p.net_worth),
    assets: Number(p.total_assets),
    liabilities: Number(p.total_liabilities),
  }));

  const startLabel = data.start
    ? new Date(data.start + "T12:00:00").toLocaleDateString("en-US", {
        month: "short",
        year: "numeric",
      })
    : "";
  const endLabel = new Date(data.end + "T12:00:00").toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
  });

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Net worth"
        subtitle={`${startLabel} – ${endLabel}`}
        action={
          <span className="text-lg font-semibold tabular-nums text-white">
            {formatMoney(currentNetWorth)}
          </span>
        }
      />
      <div className="h-64 px-2 pb-4 pt-2">
        {chartData.length < 2 ? (
          <p className="px-5 py-12 text-center text-sm text-muted">
            Not enough history yet. Sync accounts to build your net worth chart.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="nwGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(v) => formatTooltipDate(String(v))}
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                minTickGap={40}
              />
              <YAxis
                tickFormatter={formatAxis}
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={52}
              />
              <Tooltip
                contentStyle={{
                  background: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
                labelFormatter={(v) => formatTooltipDate(String(v))}
                formatter={(value: number) => [formatMoney(value), "Net worth"]}
              />
              <Area
                type="monotone"
                dataKey="netWorth"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#nwGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
