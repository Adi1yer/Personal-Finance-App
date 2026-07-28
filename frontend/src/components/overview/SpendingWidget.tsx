import { formatMoney, type MonthlyMetrics } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  data: MonthlyMetrics;
};

export default function SpendingWidget({ data }: Props) {
  const rows = [...data.spending_by_category]
    .sort((a, b) => Number(b.amount) - Number(a.amount))
    .slice(0, 6);
  const max = Math.max(...rows.map((r) => Number(r.amount)), 1);

  return (
    <Card>
      <CardHeader title="Spending" subtitle="By category this month" />
      <div className="divide-y divide-surface-border">
        {rows.length === 0 && (
          <p className="px-5 py-6 text-xs text-muted">No categorized spending yet.</p>
        )}
        {rows.map((row) => {
          const amt = Number(row.amount);
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
  );
}
