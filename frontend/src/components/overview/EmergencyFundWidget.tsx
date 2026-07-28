import { formatMoney, type OverviewResponse } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  overview: OverviewResponse;
};

export default function EmergencyFundWidget({ overview }: Props) {
  const cash = Number(overview.cash_total);
  const monthlyExpenses = Number(overview.monthly_expenses);
  const months =
    monthlyExpenses > 0 ? (cash / monthlyExpenses).toFixed(1) : null;

  return (
    <Card>
      <CardHeader title="Emergency fund" subtitle="Cash vs monthly expenses" />
      <div className="p-5">
        <p className="text-2xl font-semibold tabular-nums text-white">{formatMoney(cash)}</p>
        <p className="mt-1 text-xs text-muted">Cash accounts total</p>
        {months != null ? (
          <p className="mt-4 text-sm text-slate-300">
            Covers <span className="font-medium text-white">{months}</span> months of expenses
            <span className="text-muted"> ({formatMoney(monthlyExpenses)}/mo)</span>
          </p>
        ) : (
          <p className="mt-4 text-xs text-muted">
            Add transactions or expenses to see months-of-coverage.
          </p>
        )}
      </div>
    </Card>
  );
}
