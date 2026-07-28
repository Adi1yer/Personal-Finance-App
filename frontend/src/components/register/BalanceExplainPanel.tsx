import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { formatMoney } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  accountId: number;
};

export default function BalanceExplainPanel({ accountId }: Props) {
  const explain = useQuery({
    queryKey: ["balanceExplain", accountId],
    queryFn: () => api.balanceExplain(accountId),
  });

  if (explain.isLoading) return <p className="text-xs text-muted">Loading balance explanation…</p>;
  if (!explain.data) return null;

  const d = explain.data;
  return (
    <Card className="border-amber-500/30 bg-amber-500/5">
      <CardHeader title="Why am I off?" />
      <div className="space-y-2 p-4 text-xs text-slate-300">
        <div className="grid grid-cols-2 gap-2">
          <span>Ledger: {formatMoney(d.ledger_balance)}</span>
          {d.plaid_balance && <span>Bank: {formatMoney(d.plaid_balance)}</span>}
          {d.delta && <span className="text-amber-300">Delta: {formatMoney(d.delta)}</span>}
          <span>Uncleared: {d.uncleared_count} ({formatMoney(d.uncleared_total)})</span>
        </div>
        {d.hints.map((h) => (
          <p key={h} className="text-muted">
            {h}
          </p>
        ))}
        {d.recent_voids.length > 0 && (
          <p className="text-muted">{d.recent_voids.length} voided txn(s) in last 30 days</p>
        )}
      </div>
    </Card>
  );
}
