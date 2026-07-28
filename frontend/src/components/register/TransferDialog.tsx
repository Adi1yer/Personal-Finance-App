import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Account } from "../../api/client";
import { Button, Input, Select } from "../ui";

type Props = {
  accounts: Account[];
  defaultFromId?: number;
  onClose: () => void;
};

export default function TransferDialog({ accounts, defaultFromId, onClose }: Props) {
  const qc = useQueryClient();
  const [fromId, setFromId] = useState(String(defaultFromId ?? ""));
  const [toId, setToId] = useState("");
  const [amount, setAmount] = useState("");
  const [txnDate, setTxnDate] = useState(new Date().toISOString().slice(0, 10));

  const transfer = useMutation({
    mutationFn: () =>
      api.createTransfer({
        from_account_id: Number(fromId),
        to_account_id: Number(toId),
        amount,
        txn_date: txnDate,
        payee: "Transfer",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["register"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-surface-border bg-surface-raised p-6">
        <h2 className="text-lg font-semibold text-white">Transfer</h2>
        <div className="mt-4 space-y-3">
          <Select value={fromId} onChange={(e) => setFromId(e.target.value)}>
            <option value="">From account</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
          <Select value={toId} onChange={(e) => setToId(e.target.value)}>
            <option value="">To account</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
          <Input type="date" value={txnDate} onChange={(e) => setTxnDate(e.target.value)} />
          <Input placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => transfer.mutate()}
            disabled={!fromId || !toId || !amount || transfer.isPending}
          >
            Transfer
          </Button>
        </div>
      </div>
    </div>
  );
}
