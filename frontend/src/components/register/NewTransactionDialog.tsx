import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Account } from "../../api/client";
import { Button, Input, Select } from "../ui";

type Props = {
  account: Account;
  onClose: () => void;
};

export default function NewTransactionDialog({ account, onClose }: Props) {
  const qc = useQueryClient();
  const [txnDate, setTxnDate] = useState(new Date().toISOString().slice(0, 10));
  const [payee, setPayee] = useState("");
  const [amount, setAmount] = useState("");
  const [memo, setMemo] = useState("");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [kind, setKind] = useState<"deposit" | "withdrawal" | "charge">("withdrawal");
  const [error, setError] = useState("");

  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const accounts = useQuery({
    queryKey: ["accounts", "system"],
    queryFn: () => api.accounts(true),
  });

  const expenseAccount = accounts.data?.find((a) => a.slug === "uncategorized_expense");

  const create = useMutation({
    mutationFn: async () => {
      const amt = Math.abs(Number(amount));
      if (!amt) throw new Error("Enter an amount");
      if (account.subtype === "credit_card" && kind === "charge") {
        if (!categoryId) throw new Error("Select a category");
        if (!expenseAccount) throw new Error("Expense account missing");
        return api.createCardPurchase({
          txn_date: txnDate,
          card_account_id: account.id,
          expense_account_id: expenseAccount.id,
          category_id: Number(categoryId),
          amount: String(amt),
          payee,
          memo: memo || undefined,
        });
      }
      const signed =
        kind === "deposit" || (account.subtype === "credit_card" && kind === "withdrawal")
          ? amt
          : -amt;
      const other = expenseAccount;
      if (!other) throw new Error("Offset account missing");
      return api.createTransaction({
        txn_date: txnDate,
        payee,
        memo: memo || undefined,
        entries: [
          { account_id: account.id, amount: String(signed) },
          {
            account_id: other.id,
            amount: String(-signed),
            category_id: categoryId ? Number(categoryId) : undefined,
          },
        ],
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["register", account.id] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const isInvestment = ["brokerage", "retirement", "hsa"].includes(account.subtype);
  const isRetirement = account.subtype === "retirement";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-surface-border bg-surface-raised p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-white">New transaction</h2>
        <p className="mt-1 text-xs text-muted">{account.name}</p>
        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-muted">Type</label>
            <Select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              {account.subtype === "credit_card" ? (
                <>
                  <option value="charge">Charge</option>
                  <option value="withdrawal">Payment</option>
                </>
              ) : isInvestment ? (
                <>
                  <option value="withdrawal">
                    {isRetirement ? "Contribution / purchase" : "Purchase / outflow"}
                  </option>
                  <option value="deposit">
                    {isRetirement ? "Distribution / income" : "Sale & income"}
                  </option>
                </>
              ) : (
                <>
                  <option value="withdrawal">Withdrawal / expense</option>
                  <option value="deposit">Deposit / income</option>
                </>
              )}
            </Select>
          </div>
          <div>
            <label className="text-xs text-muted">Date</label>
            <Input type="date" value={txnDate} onChange={(e) => setTxnDate(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted">Payee</label>
            <Input value={payee} onChange={(e) => setPayee(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted">Amount</label>
            <Input
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-muted">Memo</label>
            <Input value={memo} onChange={(e) => setMemo(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted">Category</label>
            <Select
              value={categoryId}
              onChange={(e) =>
                setCategoryId(e.target.value ? Number(e.target.value) : "")
              }
            >
              <option value="">—</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </div>
          {error && <p className="text-xs text-negative">{error}</p>}
          <div className="flex gap-2 pt-2">
            <Button
              className="flex-1"
              onClick={() => create.mutate()}
              disabled={create.isPending}
            >
              Save
            </Button>
            <Button variant="secondary" className="flex-1" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
