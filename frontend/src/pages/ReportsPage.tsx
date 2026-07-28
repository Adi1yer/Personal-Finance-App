import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { api, formatMoney } from "../api/client";
import { Card, CardHeader, Button } from "../components/ui";
import { quarterRange } from "../lib/utils";
import { cn } from "../lib/utils";

type Tab = "overview" | "balance" | "income" | "cashflow" | "spending";

export default function ReportsPage() {
  const [year, setYear] = useState(2026);
  const [quarter, setQuarter] = useState(Math.ceil((new Date().getMonth() + 1) / 3));
  const [tab, setTab] = useState<Tab>("overview");
  const [exportMsg, setExportMsg] = useState("");

  const { start, end } = quarterRange(year, quarter);

  const readiness = useQuery({
    queryKey: ["reports-readiness", end],
    queryFn: () => api.reportsReadiness(end),
  });

  const metrics = useQuery({
    queryKey: ["metrics", year, quarter],
    queryFn: () => api.quarterlyMetrics(year, quarter),
    enabled: readiness.data?.ready ?? false,
  });
  const bs = useQuery({
    queryKey: ["bs", end],
    queryFn: () => api.balanceSheet(end),
    enabled: (readiness.data?.ready ?? false) && (tab === "balance" || tab === "overview"),
  });
  const inc = useQuery({
    queryKey: ["is", start, end],
    queryFn: () => api.incomeStatement(start, end),
    enabled: (readiness.data?.ready ?? false) && (tab === "income" || tab === "overview"),
  });
  const cf = useQuery({
    queryKey: ["cf", start, end],
    queryFn: () => api.cashFlowStatement(start, end),
    enabled: (readiness.data?.ready ?? false) && (tab === "cashflow" || tab === "overview"),
  });

  const priorYear = quarter === 1 ? year - 1 : year;
  const priorQuarter = quarter === 1 ? 4 : quarter - 1;
  const prior = useQuery({
    queryKey: ["metrics", priorYear, priorQuarter],
    queryFn: () => api.quarterlyMetrics(priorYear, priorQuarter),
    enabled: readiness.data?.ready ?? false,
  });

  const yoy = useQuery({
    queryKey: ["metrics", year - 1, quarter],
    queryFn: () => api.quarterlyMetrics(year - 1, quarter),
    enabled: readiness.data?.ready ?? false,
  });

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "balance", label: "Balance sheet" },
    { id: "income", label: "Income statement" },
    { id: "cashflow", label: "Cash flow" },
    { id: "spending", label: "Spending" },
  ];

  async function download(format: "csv" | "pdf") {
    setExportMsg("");
    try {
      const { blob, filename } = await api.exportReportPackage(year, quarter, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setExportMsg(`Downloaded ${filename}`);
    } catch (e) {
      setExportMsg((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Reports</h1>
          <p className="mt-1 text-sm text-muted">Quarterly financial statements</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-24 rounded-lg border border-surface-border bg-surface-overlay px-3 py-2 text-sm text-white"
          />
          <select
            value={quarter}
            onChange={(e) => setQuarter(Number(e.target.value))}
            className="rounded-lg border border-surface-border bg-surface-overlay px-3 py-2 text-sm text-white"
          >
            {[1, 2, 3, 4].map((q) => (
              <option key={q} value={q}>
                Q{q}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="secondary"
            className="gap-2"
            disabled={!readiness.data?.ready}
            onClick={() => download("csv")}
          >
            <Download className="h-4 w-4" />
            CSV
          </Button>
          <Button
            size="sm"
            variant="secondary"
            className="gap-2"
            disabled={!readiness.data?.ready}
            onClick={() => download("pdf")}
          >
            <Download className="h-4 w-4" />
            Export
          </Button>
        </div>
      </header>

      {readiness.data && !readiness.data.ready && (
        <Card className="border-negative/40 bg-negative/10 p-5">
          <p className="text-sm font-medium text-negative">
            Update 401(k) and HSA balances before generating statements
          </p>
          <ul className="mt-2 text-xs text-slate-300">
            {readiness.data.stale_accounts.map((a) => (
              <li key={a.account_id}>
                {a.account_name}: {a.reason}
                {a.last_updated ? ` (last: ${a.last_updated})` : ""}
              </li>
            ))}
          </ul>
          <Link to="/accounts" className="mt-3 inline-block text-xs text-accent hover:underline">
            Go to Accounts → Update balance
          </Link>
        </Card>
      )}

      {exportMsg && <p className="text-xs text-muted">{exportMsg}</p>}

      <div className="flex gap-1 rounded-lg border border-surface-border bg-surface-raised p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-medium transition-colors",
              tab === t.id ? "bg-accent text-white" : "text-muted hover:text-white"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {readiness.data?.ready && tab === "overview" && metrics.data && (
        <div className="grid gap-4 md:grid-cols-3">
          <ComparisonCard
            label="Net worth"
            value={formatMoney(metrics.data.net_worth)}
            qoq={metrics.data.net_worth_change}
            yoy={
              yoy.data
                ? String(Number(metrics.data.net_worth) - Number(yoy.data.net_worth))
                : null
            }
          />
          <ComparisonCard
            label="Net income"
            value={formatMoney(metrics.data.net_income)}
            qoq={
              prior.data
                ? String(Number(metrics.data.net_income) - Number(prior.data.net_income))
                : null
            }
            yoy={
              yoy.data
                ? String(Number(metrics.data.net_income) - Number(yoy.data.net_income))
                : null
            }
            positive
          />
          <Card className="p-5">
            <p className="text-xs text-muted">Savings rate</p>
            <p className="mt-2 text-2xl font-semibold">
              {metrics.data.savings_rate != null
                ? `${(Number(metrics.data.savings_rate) * 100).toFixed(1)}%`
                : "—"}
            </p>
          </Card>
        </div>
      )}

      {readiness.data?.ready && tab === "balance" && bs.data && (
        <div className="grid gap-6 lg:grid-cols-2">
          <ReportTable title="Assets" rows={bs.data.assets} total={bs.data.total_assets} />
          <ReportTable
            title="Liabilities"
            rows={bs.data.liabilities}
            total={bs.data.total_liabilities}
          />
          <Card className="lg:col-span-2 p-5">
            <p className="text-sm text-muted">Net worth as of {bs.data.as_of}</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-accent">
              {formatMoney(bs.data.net_worth)}
            </p>
          </Card>
        </div>
      )}

      {readiness.data?.ready && tab === "income" && inc.data && (
        <div className="grid gap-6 lg:grid-cols-2">
          <ReportTable title="Income" rows={inc.data.income} total={inc.data.total_income} positive />
          <ReportTable title="Expenses" rows={inc.data.expenses} total={inc.data.total_expenses} />
          <Card className="lg:col-span-2 p-5">
            <p className="text-sm text-muted">
              {inc.data.start} → {inc.data.end}
            </p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-positive">
              Net income {formatMoney(inc.data.net_income)}
            </p>
            {prior.data && (
              <p className="mt-1 text-xs text-muted">
                QoQ change:{" "}
                {formatMoney(
                  Number(inc.data.net_income) - Number(prior.data.net_income)
                )}
              </p>
            )}
          </Card>
        </div>
      )}

      {readiness.data?.ready && tab === "cashflow" && cf.data && (
        <div className="grid gap-6 lg:grid-cols-3">
          <ReportTable title="Operating" rows={cf.data.operating} total={cf.data.net_operating} />
          <ReportTable title="Investing" rows={cf.data.investing} total={cf.data.net_investing} />
          <ReportTable title="Financing" rows={cf.data.financing} total={cf.data.net_financing} />
          <Card className="lg:col-span-3 p-5">
            <p className="text-sm text-muted">
              {cf.data.start} → {cf.data.end}
            </p>
            <p className="mt-2 text-2xl font-bold tabular-nums text-white">
              Net cash change {formatMoney(cf.data.net_change)}
            </p>
          </Card>
        </div>
      )}

      {readiness.data?.ready && tab === "spending" && metrics.data && (
        <Card>
          <CardHeader title="Spending by category" subtitle={`Q${quarter} ${year}`} />
          <div className="divide-y divide-surface-border">
            {metrics.data.spending_by_category.map((row) => {
              const amt = Number(row.amount);
              const max = Math.max(
                ...metrics.data!.spending_by_category.map((r) => Number(r.amount)),
                1
              );
              return (
                <div key={row.category} className="px-5 py-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-200">{row.category}</span>
                    <span className="tabular-nums font-medium">{formatMoney(amt)}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-overlay">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${(amt / max) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}

function ComparisonCard({
  label,
  value,
  qoq,
  yoy,
  positive,
}: {
  label: string;
  value: string;
  qoq: string | null;
  yoy: string | null;
  positive?: boolean;
}) {
  return (
    <Card className="p-5">
      <p className="text-xs text-muted">{label}</p>
      <p
        className={cn(
          "mt-2 text-2xl font-semibold tabular-nums",
          positive ? "text-positive" : "text-white"
        )}
      >
        {value}
      </p>
      {qoq != null && (
        <p className="mt-1 text-xs text-muted">QoQ: {formatMoney(qoq)}</p>
      )}
      {yoy != null && <p className="text-xs text-muted">YoY: {formatMoney(yoy)}</p>}
    </Card>
  );
}

function ReportTable({
  title,
  rows,
  total,
  positive,
}: {
  title: string;
  rows: { account_name?: string; label?: string; balance?: string; total?: string; amount?: string }[];
  total: string;
  positive?: boolean;
}) {
  return (
    <Card>
      <CardHeader title={title} />
      <div className="divide-y divide-surface-border">
        {rows.map((r) => (
          <div
            key={r.account_name ?? r.label}
            className="flex justify-between px-5 py-3 text-sm"
          >
            <span className="text-slate-300">{r.account_name ?? r.label}</span>
            <span className="tabular-nums font-medium text-white">
              {formatMoney(r.balance ?? r.total ?? r.amount)}
            </span>
          </div>
        ))}
      </div>
      <div className="border-t border-surface-border px-5 py-3 text-sm font-semibold">
        <span className="text-muted">Total</span>
        <span
          className={cn("float-right tabular-nums", positive ? "text-positive" : "text-white")}
        >
          {formatMoney(total)}
        </span>
      </div>
    </Card>
  );
}
