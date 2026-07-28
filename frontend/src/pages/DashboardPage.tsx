import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  ArrowDownRight,
  ArrowUpRight,
  PiggyBank,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { api, formatMoney, type SyncHealth } from "../api/client";
import { formatPlaidSyncSummary } from "../lib/plaidSync";
import { cn } from "../lib/utils";
import { EmptyState } from "../components/ui";
import AccountTree from "../components/overview/AccountTree";
import AccountDetail from "../components/overview/AccountDetail";
import QuickActionsRail from "../components/overview/QuickActionsRail";
import CashFlowWidget from "../components/overview/CashFlowWidget";
import SpendingWidget from "../components/overview/SpendingWidget";
import EmergencyFundWidget from "../components/overview/EmergencyFundWidget";
import NetWorthChart from "../components/overview/NetWorthChart";
import SyncHealthPanel from "../components/sync/SyncHealthPanel";
import GoalProgressWidget from "../components/goals/GoalProgressWidget";

const year = new Date().getFullYear();
const quarter = Math.ceil((new Date().getMonth() + 1) / 3);
const month = new Date().getMonth() + 1;

const SCHEDULED_SYNC_MS = 6 * 60 * 60 * 1000;

function HeroStat({
  label,
  value,
  sub,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  tone?: "default" | "positive" | "negative";
}) {
  const valueColor =
    tone === "positive"
      ? "text-emerald-400"
      : tone === "negative"
        ? "text-rose-400"
        : "text-white";

  return (
    <div className="rounded-xl border border-surface-border/80 bg-surface-raised/80 p-4 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-medium uppercase tracking-wider text-muted">{label}</p>
        <Icon className="h-4 w-4 text-slate-500" />
      </div>
      <p className={cn("mt-2 text-xl font-semibold tabular-nums", valueColor)}>{value}</p>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();
  const [syncBanner, setSyncBanner] = useState("");
  const [syncHealth, setSyncHealth] = useState<SyncHealth | null>(null);

  const selectedId = searchParams.get("account")
    ? Number(searchParams.get("account"))
    : null;

  const overview = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const metrics = useQuery({
    queryKey: ["metrics", year, quarter],
    queryFn: () => api.quarterlyMetrics(year, quarter),
  });
  const monthly = useQuery({
    queryKey: ["metrics", "monthly", year, month],
    queryFn: () => api.monthlyMetrics(year, month),
  });
  const netWorthHistory = useQuery({
    queryKey: ["netWorthHistory"],
    queryFn: api.netWorthHistory,
  });
  const plaidStatus = useQuery({ queryKey: ["plaidStatus"], queryFn: api.plaidStatus });
  const plaidAccounts = useQuery({
    queryKey: ["plaidAccounts"],
    queryFn: api.plaidAccounts,
    enabled: plaidStatus.data?.configured ?? false,
  });

  const selectedAccount = useMemo(() => {
    if (!selectedId || !overview.data) return null;
    for (const g of overview.data.groups) {
      const found = g.accounts.find((a) => a.id === selectedId);
      if (found) return found;
    }
    return null;
  }, [selectedId, overview.data]);

  const setSelected = (id: number | null) => {
    if (id == null) {
      searchParams.delete("account");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ account: String(id) }, { replace: true });
    }
  };

  useEffect(() => {
    if (!plaidStatus.data?.configured) return;
    const hasMapped = plaidAccounts.data?.some((a) => a.ledger_account_id);
    if (!hasMapped) return;

    const runScheduledSync = () => {
      api
        .plaidScheduledSync()
        .then((r) => {
          if (r.ran) {
            setSyncBanner(formatPlaidSyncSummary(r));
            qc.invalidateQueries({ queryKey: ["overview"] });
            qc.invalidateQueries({ queryKey: ["metrics"] });
            qc.invalidateQueries({ queryKey: ["netWorthHistory"] });
            qc.invalidateQueries({ queryKey: ["accounts"] });
            qc.invalidateQueries({ queryKey: ["plaidStatus"] });
          }
        })
        .catch(() => {
          /* scheduled sync is best-effort */
        });
    };

    runScheduledSync();
    const id = window.setInterval(runScheduledSync, SCHEDULED_SYNC_MS);
    return () => window.clearInterval(id);
  }, [plaidStatus.data, plaidAccounts.data, qc]);

  if (overview.isLoading) {
    return <p className="text-sm text-muted">Loading overview…</p>;
  }

  if (overview.error || !overview.data) {
    return (
      <EmptyState
        title="Could not load overview"
        description={(overview.error as Error)?.message ?? "Unknown error"}
      />
    );
  }

  const plaidReady = Boolean(plaidStatus.data?.enabled && plaidStatus.data?.configured);
  const nwChange = metrics.data?.net_worth_change;
  const nwUp = nwChange != null && Number(nwChange) >= 0;

  return (
    <div className="-mx-8 -mt-2 flex min-h-[calc(100vh-3.5rem)] flex-col">
      {syncBanner && (
        <div className="border-b border-accent/30 bg-accent/10 px-4 py-2 text-xs text-accent">
          {syncBanner}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <div className="w-64 shrink-0">
          <AccountTree
            data={overview.data}
            selectedId={selectedId}
            onSelect={setSelected}
          />
        </div>
        <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          {selectedAccount ? (
            <div className="px-6 py-6">
              <AccountDetail account={selectedAccount} />
            </div>
          ) : (
            <div className="space-y-6 px-6 py-6">
              <div className="relative overflow-hidden rounded-2xl border border-surface-border bg-gradient-to-br from-slate-900 via-surface-raised to-slate-900 p-6 shadow-card">
                <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-accent/10 blur-3xl" />
                <div className="relative">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted">
                    Total net worth
                  </p>
                  <div className="mt-2 flex flex-wrap items-end gap-4">
                    <h1 className="text-4xl font-bold tabular-nums tracking-tight text-white">
                      {formatMoney(overview.data.net_worth)}
                    </h1>
                    {nwChange != null && (
                      <span
                        className={cn(
                          "mb-1 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
                          nwUp
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-rose-500/15 text-rose-400"
                        )}
                      >
                        {nwUp ? (
                          <ArrowUpRight className="h-3.5 w-3.5" />
                        ) : (
                          <ArrowDownRight className="h-3.5 w-3.5" />
                        )}
                        {formatMoney(nwChange)} vs Q{quarter === 1 ? 4 : quarter - 1}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    Assets {formatMoney(overview.data.total_assets)} · Liabilities{" "}
                    {formatMoney(overview.data.total_liabilities)}
                  </p>
                </div>
              </div>

              {overview.data.goals_progress && (
                <GoalProgressWidget goals={overview.data.goals_progress} />
              )}

              {(syncHealth || overview.data.advisor_insights) && (
                <SyncHealthPanel health={syncHealth} insights={overview.data.advisor_insights} />
              )}

              {netWorthHistory.data && (
                <NetWorthChart
                  data={netWorthHistory.data}
                  currentNetWorth={overview.data.net_worth}
                />
              )}

              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <HeroStat
                  label="Income (quarter)"
                  value={formatMoney(metrics.data?.total_income)}
                  icon={TrendingUp}
                  tone="positive"
                />
                <HeroStat
                  label="Expenses (quarter)"
                  value={formatMoney(metrics.data?.total_expenses)}
                  icon={Wallet}
                  tone="negative"
                />
                <HeroStat
                  label="Savings rate"
                  value={
                    metrics.data?.savings_rate != null
                      ? `${(Number(metrics.data.savings_rate) * 100).toFixed(1)}%`
                      : "—"
                  }
                  sub="Quarter to date"
                  icon={PiggyBank}
                />
                <HeroStat
                  label="Cash on hand"
                  value={formatMoney(overview.data.cash_total)}
                  sub="Checking & savings"
                  icon={Wallet}
                />
              </div>
            </div>
          )}

          {monthly.data && !selectedAccount && (
            <div className="grid gap-4 px-6 pb-6 lg:grid-cols-3">
              <CashFlowWidget data={monthly.data} />
              <SpendingWidget data={monthly.data} />
              <EmergencyFundWidget overview={overview.data} />
            </div>
          )}
        </div>
        <div className="hidden w-52 shrink-0 border-l border-surface-border p-4 xl:block">
          <QuickActionsRail
            plaidReady={plaidReady}
            onSyncDone={setSyncBanner}
            onHealth={setSyncHealth}
          />
        </div>
      </div>
    </div>
  );
}
