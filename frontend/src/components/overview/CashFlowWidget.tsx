import { formatMoney, type MonthlyMetrics } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  data: MonthlyMetrics;
};

function Bar({
  label,
  current,
  prior,
  positive,
}: {
  label: string;
  current: number;
  prior: number;
  positive?: boolean;
}) {
  const max = Math.max(Math.abs(current), Math.abs(prior), 1);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className={positive ? "text-positive" : "text-negative"}>
          {formatMoney(current)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-overlay">
        <div
          className={`h-full rounded-full ${positive ? "bg-emerald-500" : "bg-rose-500"}`}
          style={{ width: `${(Math.abs(current) / max) * 100}%` }}
        />
      </div>
      <p className="text-[10px] text-muted">Prior: {formatMoney(prior)}</p>
    </div>
  );
}

export default function CashFlowWidget({ data }: Props) {
  const monthLabel = new Date(data.year, data.month - 1).toLocaleString("en-US", {
    month: "long",
    year: "numeric",
  });

  return (
    <Card>
      <CardHeader title="Cash flow" subtitle={monthLabel} />
      <div className="space-y-4 p-5">
        <Bar
          label="Income this month"
          current={Number(data.total_income)}
          prior={Number(data.prior_total_income)}
          positive
        />
        <Bar
          label="Expenses this month"
          current={Number(data.total_expenses)}
          prior={Number(data.prior_total_expenses)}
        />
        <p className="border-t border-surface-border pt-3 text-sm">
          <span className="text-muted">Net </span>
          <span
            className={
              Number(data.net_income) >= 0 ? "font-medium text-positive" : "font-medium text-negative"
            }
          >
            {formatMoney(data.net_income)}
          </span>
        </p>
      </div>
    </Card>
  );
}
