import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, formatMoney } from "../../api/client";
import { Button, Input } from "../ui";
import { cn } from "../../lib/utils";

type Props = {
  accountId: number;
  onClose: () => void;
};

function entryAmount(charge: string | null, payment: string | null): number {
  if (payment) return Number(payment);
  if (charge) return -Number(charge);
  return 0;
}

export default function ReconcilePanel({ accountId, onClose }: Props) {
  const qc = useQueryClient();
  const [endDate, setEndDate] = useState("");
  const [balance, setBalance] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const preview = useQuery({
    queryKey: ["reconcile-preview", accountId, endDate, balance],
    queryFn: () => api.reconcilePreview(accountId, endDate, balance),
    enabled: Boolean(endDate && balance),
  });

  useEffect(() => {
    if (preview.data) {
      setSelected(new Set(preview.data.uncleared_entries.map((e) => e.entry_id)));
    }
  }, [preview.data]);

  const liveDifference = useMemo(() => {
    if (!preview.data || !balance) return null;
    const target = Number(balance);
    const selectedSum = preview.data.uncleared_entries.reduce((sum, e) => {
      if (!selected.has(e.entry_id)) return sum;
      return sum + entryAmount(e.charge, e.payment);
    }, 0);
    const projectedCleared = Number(preview.data.cleared_balance) + selectedSum;
    return target - projectedCleared;
  }, [preview.data, balance, selected]);

  const finish = useMutation({
    mutationFn: () =>
      api.reconcileAccount(accountId, {
        statement_end_date: endDate,
        ending_balance: balance,
        cleared_entry_ids: Array.from(selected),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["register", accountId] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      onClose();
    },
  });

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (!preview.data) return;
    setSelected(new Set(preview.data.uncleared_entries.map((e) => e.entry_id)));
  };

  const selectNone = () => setSelected(new Set());

  const balanced = liveDifference != null && Math.abs(liveDifference) < 0.005;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-surface-border bg-surface-raised shadow-xl">
        <div className="border-b border-surface-border p-5">
          <h2 className="text-lg font-semibold text-white">Reconcile account</h2>
          <p className="mt-1 text-xs text-muted">
            Match transactions on your statement, then finish when the difference is zero.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted">Statement end</label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted">Ending balance</label>
              <Input
                type="number"
                step="0.01"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
              />
            </div>
          </div>
          {preview.data && (
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <span className="text-muted">
                Ledger: {formatMoney(preview.data.ledger_balance)}
              </span>
              <span className="text-muted">
                Target: {formatMoney(preview.data.ending_balance)}
              </span>
              <span
                className={cn(
                  "col-span-2 font-medium",
                  balanced ? "text-positive" : "text-negative"
                )}
              >
                Difference:{" "}
                {liveDifference != null
                  ? formatMoney(String(liveDifference))
                  : formatMoney(preview.data.difference)}
                {balanced && " — balanced"}
              </span>
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {preview.isLoading && <p className="text-sm text-muted">Loading…</p>}
          {preview.data?.uncleared_entries.length === 0 && (
            <p className="text-sm text-muted">No uncleared transactions through this date.</p>
          )}
          {preview.data && preview.data.uncleared_entries.length > 0 && (
            <p className="mb-3 text-xs text-muted">
              Select statement items to mark cleared ({selected.size} selected)
            </p>
          )}
          <ul className="space-y-2">
            {preview.data?.uncleared_entries.map((e) => (
              <li key={e.entry_id}>
                <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-surface-border px-3 py-2 text-sm hover:bg-surface-overlay/40">
                  <input
                    type="checkbox"
                    checked={selected.has(e.entry_id)}
                    onChange={() => toggle(e.entry_id)}
                  />
                  <span className="text-slate-400">{e.txn_date}</span>
                  <span className="flex-1 truncate text-white">{e.payee}</span>
                  <span className="tabular-nums">
                    {e.charge
                      ? formatMoney(e.charge)
                      : e.payment
                        ? formatMoney(e.payment)
                        : ""}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-wrap gap-2 border-t border-surface-border p-5">
          <Button variant="secondary" onClick={selectAll}>
            Select all
          </Button>
          <Button variant="secondary" onClick={selectNone}>
            Clear selection
          </Button>
          <Button
            className="flex-1"
            disabled={!endDate || !balance || finish.isPending || !balanced}
            onClick={() => finish.mutate()}
          >
            Finish reconcile
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
