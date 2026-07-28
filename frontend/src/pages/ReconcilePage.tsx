import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, formatMoney } from "../api/client";
import { Card, CardHeader, Select, Input, Button } from "../components/ui";
import { Scale } from "lucide-react";

export default function ReconcilePage() {
  const [searchParams] = useSearchParams();
  const initial = searchParams.get("account");
  const qc = useQueryClient();
  const [accountId, setAccountId] = useState<number | "">(
    initial ? Number(initial) : ""
  );
  const [endDate, setEndDate] = useState("");
  const [balance, setBalance] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState("");

  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => api.accounts() });
  const reconcileable = accounts.data?.filter((a) =>
    ["checking", "credit_card"].includes(a.subtype)
  );

  const preview = useQuery({
    queryKey: ["reconcile-preview", accountId, endDate, balance],
    queryFn: () => api.reconcilePreview(Number(accountId), endDate, balance),
    enabled: Boolean(accountId && endDate && balance),
  });

  useEffect(() => {
    if (preview.data) {
      setSelected(new Set(preview.data.uncleared_entries.map((e) => e.entry_id)));
    }
  }, [preview.data]);

  const finish = useMutation({
    mutationFn: () =>
      api.reconcileAccount(Number(accountId), {
        statement_end_date: endDate,
        ending_balance: balance,
        cleared_entry_ids: Array.from(selected),
      }),
    onSuccess: () => {
      setMessage("Reconciliation saved.");
      qc.invalidateQueries({ queryKey: ["register"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-white">Reconcile</h1>
        <p className="mt-1 text-sm text-muted">
          Match your ledger to bank statement ending balance
        </p>
      </header>

      <Card>
        <CardHeader title="Statement reconciliation" subtitle="Checking and credit cards" />
        <div className="space-y-4 p-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Account</label>
            <Select
              value={accountId}
              onChange={(e) =>
                setAccountId(e.target.value ? Number(e.target.value) : "")
              }
            >
              <option value="">Select…</option>
              {reconcileable?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Statement end date
              </label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Ending balance
              </label>
              <Input
                type="number"
                step="0.01"
                placeholder="0.00"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
              />
            </div>
          </div>

          {preview.data && (
            <div className="rounded-lg border border-surface-border bg-surface-overlay/40 p-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">Ledger balance</span>
                <span>{formatMoney(preview.data.ledger_balance)}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-muted">Difference</span>
                <span
                  className={
                    Number(preview.data.difference) === 0
                      ? "text-positive"
                      : "text-negative"
                  }
                >
                  {formatMoney(preview.data.difference)}
                </span>
              </div>
            </div>
          )}

          {preview.data && preview.data.uncleared_entries.length > 0 && (
            <div className="max-h-64 overflow-y-auto rounded-lg border border-surface-border">
              {preview.data.uncleared_entries.map((e) => (
                <label
                  key={e.entry_id}
                  className="flex cursor-pointer items-center gap-3 border-b border-surface-border/50 px-3 py-2 text-sm last:border-0 hover:bg-surface-overlay/30"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(e.entry_id)}
                    onChange={() => toggle(e.entry_id)}
                  />
                  <span className="text-slate-400">{e.txn_date}</span>
                  <span className="flex-1 truncate">{e.payee}</span>
                  <span className="tabular-nums">
                    {e.charge
                      ? formatMoney(e.charge)
                      : e.payment
                        ? formatMoney(e.payment)
                        : ""}
                  </span>
                </label>
              ))}
            </div>
          )}

          <Button
            type="button"
            disabled={!accountId || !endDate || !balance || finish.isPending}
            className="w-full gap-2"
            onClick={() => finish.mutate()}
          >
            <Scale className="h-4 w-4" />
            Finish reconciliation
          </Button>
          {message && <p className="text-center text-xs text-muted">{message}</p>}
        </div>
      </Card>
    </div>
  );
}
