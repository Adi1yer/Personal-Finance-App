import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatMoney, type Account } from "../api/client";
import AccountFormModal from "../components/AccountFormModal";
import { Card, Badge, EmptyState, Button, Input, Select, CardHeader } from "../components/ui";
import { Building2, CreditCard, TrendingUp, PiggyBank, Plus, Pencil, Archive } from "lucide-react";

const SYSTEM_SLUGS = new Set([
  "uncategorized_expense",
  "salary_income",
  "other_income",
  "opening_equity",
]);

const typeMeta: Record<string, { label: string; icon: typeof Building2 }> = {
  asset: { label: "Assets", icon: TrendingUp },
  liability: { label: "Liabilities", icon: CreditCard },
  income: { label: "Income", icon: PiggyBank },
  expense: { label: "Expenses", icon: Building2 },
  equity: { label: "Equity", icon: Building2 },
};

export default function AccountsPage() {
  const qc = useQueryClient();
  const [modal, setModal] = useState<"add" | number | null>(null);
  const [markAccountId, setMarkAccountId] = useState<number | "">("");
  const [markDate, setMarkDate] = useState("");
  const [markValue, setMarkValue] = useState("");
  const [markContribution, setMarkContribution] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.accounts(),
  });

  const archive = useMutation({
    mutationFn: (id: number) => api.archiveAccount(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const saveMark = useMutation({
    mutationFn: () =>
      api.createAccountMark({
        account_id: Number(markAccountId),
        as_of_date: markDate,
        market_value: markValue,
        ...(markContribution.trim() && !selectedIsPlaid
          ? { total_contributions: markContribution.trim() }
          : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["reports-readiness"] });
      qc.invalidateQueries({ queryKey: ["netWorthHistory"] });
      qc.invalidateQueries({ queryKey: ["goalsProgress"] });
      setMarkAccountId("");
      setMarkDate("");
      setMarkValue("");
      setMarkContribution("");
    },
  });

  const userAccounts = data?.filter((a) => !SYSTEM_SLUGS.has(a.slug)) ?? [];
  const editAccount =
    typeof modal === "number" ? data?.find((a) => a.id === modal) : null;

  if (isLoading) return <p className="text-sm text-muted">Loading accounts…</p>;
  if (error) {
    return (
      <div className="rounded-lg border border-negative/30 bg-negative/10 p-4 text-sm text-negative">
        {(error as Error).message}
      </div>
    );
  }

  const manualMarkAccounts = userAccounts.filter((a) =>
    ["brokerage", "retirement", "hsa"].includes(a.subtype)
  );
  const selectedMarkAccount = manualMarkAccounts.find((a) => a.id === markAccountId);
  const selectedIsPlaid = selectedMarkAccount?.sync_source === "plaid";

  const groups = ["asset", "liability", "income", "expense", "equity"] as const;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Accounts</h1>
          <p className="mt-1 text-sm text-muted">
            Add and name your accounts — checking, cards, retirement, HSA
          </p>
        </div>
        <Button className="gap-2" onClick={() => setModal("add")}>
          <Plus className="h-4 w-4" />
          Add account
        </Button>
      </header>

      {userAccounts.length === 0 && (
        <EmptyState
          title="No accounts yet"
          description="Click Add account to create your checking, credit cards, and investment accounts with your own names."
        />
      )}

      {groups.map((type) => {
        const visible =
          data?.filter(
            (a) => a.account_type === type && !SYSTEM_SLUGS.has(a.slug)
          ) ?? [];
        if (!visible.length) return null;
        const meta = typeMeta[type];
        const Icon = meta.icon;

        return (
          <section key={type}>
            <div className="mb-3 flex items-center gap-2">
              <Icon className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
                {meta.label}
              </h2>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map((a) => (
                <Card key={a.id} className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-medium text-white">{a.name}</p>
                    <div className="flex gap-1">
                      {!SYSTEM_SLUGS.has(a.slug) && (
                        <>
                          <button
                            type="button"
                            className="text-muted hover:text-white"
                            onClick={() => setModal(a.id)}
                            aria-label="Edit"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            className="text-muted hover:text-negative"
                            onClick={() => archive.mutate(a.id)}
                            aria-label="Archive"
                          >
                            <Archive className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <Badge tone={a.sync_source === "plaid" ? "blue" : "neutral"}>
                    {a.sync_source} · {a.subtype.replace("_", " ")}
                  </Badge>
                  <p className="mt-3 text-xl font-semibold tabular-nums">
                    {formatMoney(a.balance)}
                  </p>
                </Card>
              ))}
            </div>
          </section>
        );
      })}

      <Card>
        <CardHeader
          title="Update balance (401k, HSA, brokerage)"
          subtitle="Checking and credit cards update from transactions or Plaid — not here"
        />
        {manualMarkAccounts.length === 0 ? (
          <p className="px-5 py-4 text-sm text-muted">
            Add a retirement, HSA, or brokerage account above to set a manual balance mark.
          </p>
        ) : (
          <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
            <div className="sm:col-span-2 lg:col-span-1">
              <label className="mb-1.5 block text-xs font-medium text-muted">Account</label>
              <Select
                value={markAccountId}
                onChange={(e) => {
                  setMarkAccountId(e.target.value ? Number(e.target.value) : "");
                  setMarkContribution("");
                }}
              >
                <option value="">Select account…</option>
                {manualMarkAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">As of date</label>
              <Input
                type="date"
                value={markDate}
                onChange={(e) => setMarkDate(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Market value</label>
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={markValue}
                onChange={(e) => setMarkValue(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Total contributions
              </label>
              {selectedIsPlaid ? (
                <p className="rounded-md border border-surface-border px-3 py-2 text-xs text-muted">
                  Pulled from Plaid when Chase labels a deposit or contribution
                </p>
              ) : (
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  value={markContribution}
                  onChange={(e) => setMarkContribution(e.target.value)}
                  disabled={!markAccountId}
                />
              )}
            </div>
            <div>
              <Button
                className="w-full sm:w-auto"
                disabled={!markAccountId || !markDate || !markValue || saveMark.isPending}
                onClick={() => saveMark.mutate()}
              >
                {saveMark.isPending ? "Saving…" : "Save balance"}
              </Button>
            </div>
          </div>
        )}
      </Card>

      <FundHoldingsSection accounts={manualMarkAccounts.filter((a) => ["retirement", "hsa"].includes(a.subtype))} />

      {(modal === "add" || editAccount) && (
        <AccountFormModal
          account={editAccount}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}

function FundHoldingsSection({ accounts }: { accounts: Account[] }) {
  const qc = useQueryClient();
  const [accountId, setAccountId] = useState<number | "">("");
  const [ticker, setTicker] = useState("");
  const [weight, setWeight] = useState("");

  const holdings = useQuery({
    queryKey: ["fundHoldings", accountId],
    queryFn: () => api.fundHoldings(Number(accountId)),
    enabled: accountId !== "",
  });

  const add = useMutation({
    mutationFn: () =>
      api.createFundHolding(Number(accountId), {
        ticker,
        allocation_pct: weight,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fundHoldings", accountId] });
      setTicker("");
      setWeight("");
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteFundHolding(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fundHoldings", accountId] }),
  });

  if (!accounts.length) return null;

  return (
    <Card>
      <CardHeader title="401(k) / HSA fund breakdown" subtitle="For dividend projections" />
      <div className="space-y-3 p-4">
        <Select value={accountId} onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Select account…</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        {accountId && (
          <>
            <div className="flex gap-2">
              <Input placeholder="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value)} />
              <Input placeholder="Weight %" value={weight} onChange={(e) => setWeight(e.target.value)} />
              <Button size="sm" onClick={() => add.mutate()} disabled={!ticker || !weight}>
                Add
              </Button>
            </div>
            <ul className="text-sm text-muted">
              {holdings.data?.map((h) => (
                <li key={h.id} className="flex justify-between py-1">
                  <span>
                    {h.ticker} {h.allocation_pct ? `· ${h.allocation_pct}%` : ""}
                  </span>
                  <button type="button" className="text-negative" onClick={() => remove.mutate(h.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Card>
  );
}
