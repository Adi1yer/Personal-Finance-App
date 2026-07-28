import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw, Plus, Scale, Search, X } from "lucide-react";
import { api, formatMoney } from "../api/client";
import { formatPlaidSyncSummary } from "../lib/plaidSync";
import AccountTree from "../components/overview/AccountTree";
import RegisterTable from "../components/register/RegisterTable";
import PositionsStrip from "../components/register/PositionsStrip";
import NewTransactionDialog from "../components/register/NewTransactionDialog";
import BalanceExplainPanel from "../components/register/BalanceExplainPanel";
import TransferDialog from "../components/register/TransferDialog";
import ReconcilePanel from "../components/register/ReconcilePanel";
import { Badge, Button, EmptyState, Input } from "../components/ui";
import { cn } from "../lib/utils";

type RegisterFilter = "all" | "uncleared";

export default function RegisterPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();
  const initial = searchParams.get("account");
  const [accountId, setAccountId] = useState<number | null>(
    initial ? Number(initial) : null
  );
  const [focusedEntryId, setFocusedEntryId] = useState<number | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [showReconcile, setShowReconcile] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [showBalanceExplain, setShowBalanceExplain] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");
  const [filter, setFilter] = useState<RegisterFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const overview = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => api.accounts() });

  const register = useQuery({
    queryKey: ["register", accountId],
    queryFn: () => api.accountRegister(accountId!),
    enabled: accountId != null,
  });

  const sync = useMutation({
    mutationFn: api.plaidSync,
    onSuccess: (r) => {
      setSyncMsg(formatPlaidSyncSummary(r));
      qc.invalidateQueries({ queryKey: ["register"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const selectedAccount = accounts.data?.find((a) => a.id === accountId);

  const baseRows = useMemo(() => {
    if (!register.data) return [];
    if (filter === "uncleared") {
      return register.data.rows.filter((r) => !r.is_cleared);
    }
    return register.data.rows;
  }, [register.data, filter]);

  const isInvestmentAccount =
    register.data?.account_subtype != null &&
    ["brokerage", "retirement", "hsa"].includes(register.data.account_subtype);

  const visibleRows = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return baseRows;
    return baseRows.filter((row) => {
      return (
        row.payee.toLowerCase().includes(q) ||
        (row.memo?.toLowerCase().includes(q) ?? false) ||
        (row.category_name?.toLowerCase().includes(q) ?? false) ||
        (row.security_name?.toLowerCase().includes(q) ?? false) ||
        (row.activity_label?.toLowerCase().includes(q) ?? false) ||
        (row.investment_type?.toLowerCase().includes(q) ?? false) ||
        row.txn_date.includes(q)
      );
    });
  }, [baseRows, searchQuery]);

  const setSelected = (id: number | null) => {
    setAccountId(id);
    setFocusedEntryId(null);
    setFilter("all");
    setSearchQuery("");
    if (id == null) {
      searchParams.delete("account");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ account: String(id) }, { replace: true });
    }
  };

  const plaidMismatch = useMemo(() => {
    if (!register.data?.plaid_balance_current) return false;
    const plaid = Number(register.data.plaid_balance_current);
    if (isInvestmentAccount) {
      const portfolio = Number(
        register.data.portfolio_value ?? register.data.current_balance
      );
      return Math.abs(plaid - portfolio) > 1;
    }
    return register.data.plaid_balance_current !== register.data.current_balance;
  }, [register.data, isInvestmentAccount]);

  useEffect(() => {
    setFocusedEntryId(null);
  }, [filter]);

  const clearFocusUnlessRow = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    if (!target.closest("[data-register-row]")) {
      setFocusedEntryId(null);
    }
  };

  if (overview.isLoading) {
    return <p className="text-sm text-muted">Loading…</p>;
  }

  if (!overview.data) {
    return <EmptyState title="Could not load accounts" description="Try refreshing the page." />;
  }

  return (
    <div className="-mx-8 -mt-2 flex min-h-[calc(100vh-3.5rem)] flex-col">
      {syncMsg && (
        <div className="border-b border-accent/30 bg-accent/10 px-4 py-2 text-xs text-accent">
          {syncMsg}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 border-b border-surface-border px-4 py-3" onClick={clearFocusUnlessRow}>
        <Button
          size="sm"
          variant="secondary"
          className="gap-2"
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
        >
          <RefreshCw className={sync.isPending ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          Sync now
        </Button>
        {accountId && (
          <>
            <Button size="sm" variant="secondary" className="gap-2" onClick={() => setShowNew(true)}>
              <Plus className="h-4 w-4" />
              New transaction
            </Button>
            <Button size="sm" variant="secondary" className="gap-2" onClick={() => setShowTransfer(true)}>
              Transfer
            </Button>
            {selectedAccount &&
              ["checking", "credit_card"].includes(selectedAccount.subtype) && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="gap-2"
                  onClick={() => setShowReconcile(true)}
                >
                  <Scale className="h-4 w-4" />
                  Reconcile
                </Button>
              )}
            <div className="ml-1 flex items-center gap-1 rounded-lg border border-surface-border p-0.5">
              <button
                type="button"
                onClick={() => setFilter("all")}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  filter === "all"
                    ? "bg-surface-overlay text-white"
                    : "text-muted hover:text-white"
                )}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setFilter("uncleared")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  filter === "uncleared"
                    ? "bg-surface-overlay text-white"
                    : "text-muted hover:text-white"
                )}
              >
                Uncleared
                {register.data && register.data.uncleared_count > 0 && (
                  <span className="rounded-full bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent">
                    {register.data.uncleared_count}
                  </span>
                )}
              </button>
            </div>
            <div className="relative ml-2 min-w-[200px] flex-1 max-w-sm">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search transactions…"
                className="h-8 pl-8 pr-8 text-xs"
              />
              {searchQuery && (
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-white"
                  onClick={() => setSearchQuery("")}
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </>
        )}
        {register.data?.tracking_start_date && (
          <Badge tone="neutral">
            Tracking from{" "}
            {new Date(`${register.data.tracking_start_date}T12:00:00`).toLocaleDateString(
              undefined,
              { month: "short", day: "numeric", year: "numeric" }
            )}
          </Badge>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="w-64 shrink-0" onClick={clearFocusUnlessRow}>
          <AccountTree
            data={overview.data}
            selectedId={accountId}
            onSelect={setSelected}
          />
        </div>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {!accountId && (
            <div className="m-8">
              <EmptyState
                title="Select an account"
                description="Choose an account in the tree to view its register."
              />
            </div>
          )}
          {accountId && register.data && (
            <>
              <div
                className="flex items-center justify-between border-b border-surface-border px-6 py-4"
                onClick={clearFocusUnlessRow}
              >
                <div>
                  <h1 className="text-xl font-semibold text-white">
                    {register.data.account_name}
                  </h1>
                  <p className="mt-0.5 text-xs text-muted">
                    {searchQuery.trim()
                      ? `${visibleRows.length} of ${baseRows.length} transactions`
                      : `${register.data.total_count} transactions`}
                    {register.data.uncleared_count > 0 && (
                      <> · {register.data.uncleared_count} uncleared</>
                    )}
                    {selectedAccount?.sync_source === "manual" && " · Manual account"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-semibold tabular-nums text-white">
                    {formatMoney(
                      isInvestmentAccount
                        ? register.data.portfolio_value ?? register.data.current_balance
                        : register.data.current_balance
                    )}
                  </p>
                  {isInvestmentAccount && register.data.cash_balance != null && (
                    <p className="mt-0.5 text-xs text-muted">
                      Cash balance: {formatMoney(register.data.cash_balance)}
                    </p>
                  )}
                  {plaidMismatch && register.data.plaid_balance_current && (
                    <div className="mt-1">
                      <button
                        type="button"
                        className="text-xs text-amber-400 underline"
                        onClick={() => setShowBalanceExplain((v) => !v)}
                      >
                        Bank: {formatMoney(register.data.plaid_balance_current)} — Why am I off?
                      </button>
                    </div>
                  )}
                </div>
              </div>
              {showBalanceExplain && accountId && (
                <div className="px-4 pb-2">
                  <BalanceExplainPanel accountId={accountId} />
                </div>
              )}
              {isInvestmentAccount && register.data.holdings.length > 0 && (
                <PositionsStrip
                  holdings={register.data.holdings}
                  cashBalance={register.data.cash_balance}
                  asOfDate={register.data.holdings_as_of_date}
                />
              )}
              <div className="flex-1 overflow-auto" onClick={clearFocusUnlessRow}>
                <RegisterTable
                  rows={visibleRows}
                  openingBalance={register.data.opening_balance}
                  searchActive={searchQuery.trim().length > 0}
                  accountSubtype={register.data.account_subtype}
                  balanceColumnLabel={register.data.balance_column_label}
                  categories={categories.data ?? []}
                  accountId={accountId}
                  amountOutLabel={register.data.amount_out_label}
                  amountInLabel={register.data.amount_in_label}
                  focusedEntryId={focusedEntryId}
                  onFocusEntry={setFocusedEntryId}
                  clearedBalance={register.data.cleared_balance}
                  unclearedBalance={register.data.uncleared_balance}
                  filter={filter}
                />
              </div>
            </>
          )}
          {accountId && register.isLoading && (
            <p className="p-8 text-sm text-muted">Loading register…</p>
          )}
        </div>
      </div>

      {showNew && selectedAccount && (
        <NewTransactionDialog account={selectedAccount} onClose={() => setShowNew(false)} />
      )}
      {showTransfer && accounts.data && (
        <TransferDialog
          accounts={accounts.data}
          defaultFromId={accountId ?? undefined}
          onClose={() => setShowTransfer(false)}
        />
      )}
      {showReconcile && accountId && (
        <ReconcilePanel accountId={accountId} onClose={() => setShowReconcile(false)} />
      )}
    </div>
  );
}
