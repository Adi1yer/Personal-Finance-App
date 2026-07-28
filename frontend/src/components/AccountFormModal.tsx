import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Account, type AccountInput } from "../api/client";
import { Button, Input, Select } from "./ui";

const SUBTYPES_BY_TYPE: Record<string, { value: string; label: string }[]> = {
  asset: [
    { value: "checking", label: "Checking" },
    { value: "brokerage", label: "Brokerage" },
    { value: "retirement", label: "Retirement (401k, IRA)" },
    { value: "hsa", label: "HSA" },
    { value: "other", label: "Other asset" },
  ],
  liability: [{ value: "credit_card", label: "Credit card" }],
  income: [{ value: "other", label: "Income" }],
  expense: [{ value: "other", label: "Expense" }],
  equity: [{ value: "other", label: "Equity" }],
};

type Props = {
  account?: Account | null;
  onClose: () => void;
};

export default function AccountFormModal({ account, onClose }: Props) {
  const qc = useQueryClient();
  const [name, setName] = useState(account?.name ?? "");
  const [accountType, setAccountType] = useState(account?.account_type ?? "asset");
  const [subtype, setSubtype] = useState(account?.subtype ?? "checking");
  const [error, setError] = useState("");

  const save = useMutation({
    mutationFn: async () => {
      const body: AccountInput = {
        name: name.trim(),
        account_type: accountType,
        subtype,
        sync_source: account?.sync_source ?? "manual",
      };
      if (account) {
        return api.updateAccount(account.id, body);
      }
      return api.createAccount(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      onClose();
    },
    onError: (e) => setError((e as Error).message),
  });

  const subtypes = SUBTYPES_BY_TYPE[accountType] ?? SUBTYPES_BY_TYPE.asset;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="no-drag w-full max-w-md rounded-xl border border-surface-border bg-surface-raised p-6 shadow-card">
        <h2 className="text-lg font-semibold text-white">
          {account ? "Edit account" : "Add account"}
        </h2>
        <p className="mt-1 text-xs text-muted">
          Add checking, credit cards, retirement, and HSA with your own names.
        </p>
        <div className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted">Display name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Chase Sapphire, Empower 401k"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Type</label>
            <Select
              value={accountType}
              onChange={(e) => {
                setAccountType(e.target.value);
                const first = SUBTYPES_BY_TYPE[e.target.value]?.[0];
                if (first) setSubtype(first.value);
              }}
              disabled={!!account && account.slug.startsWith("uncategorized")}
            >
              <option value="asset">Asset</option>
              <option value="liability">Liability</option>
              <option value="income">Income</option>
              <option value="expense">Expense</option>
              <option value="equity">Equity</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Subtype</label>
            <Select value={subtype} onChange={(e) => setSubtype(e.target.value)}>
              {subtypes.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
            {accountType === "liability" && (
              <p className="mt-1.5 text-[11px] text-muted">
                Credit card balances update from transactions or Plaid sync.
              </p>
            )}
          </div>
        </div>
        {error && <p className="mt-3 text-xs text-negative">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => save.mutate()}
            disabled={!name.trim() || save.isPending}
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}
