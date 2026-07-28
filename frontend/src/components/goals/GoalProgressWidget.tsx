import { formatMoney, type GoalsProgress } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  goals: GoalsProgress;
};

function ProgressBar({ pct }: { pct: number }) {
  const clamped = Math.min(100, Math.max(0, pct));
  return (
    <div className="h-2 overflow-hidden rounded-full bg-surface-overlay">
      <div className="h-full bg-accent transition-all" style={{ width: `${clamped}%` }} />
    </div>
  );
}

export default function GoalProgressWidget({ goals }: Props) {
  const investPct =
    Number(goals.investing.pace_target) > 0
      ? (Number(goals.investing.ytd_actual) / Number(goals.investing.pace_target)) * 100
      : 0;
  const safetyPct =
    Number(goals.safety_net.target_balance) > 0
      ? (Number(goals.safety_net.current_balance) / Number(goals.safety_net.target_balance)) * 100
      : 0;
  const byAccount = goals.investing.by_account ?? [];

  return (
    <Card>
      <CardHeader title={`${goals.year} goals`} />
      <div className="space-y-4 p-4 text-xs">
        <div>
          <div className="mb-1 flex justify-between text-muted">
            <span>Investing ({goals.investing.pct_of_income}% of income)</span>
            <span>
              {formatMoney(goals.investing.ytd_actual)} / {formatMoney(goals.investing.pace_target)} YTD pace
            </span>
          </div>
          <ProgressBar pct={investPct} />
          {byAccount.length > 0 && (
            <ul className="mt-2 space-y-1 text-muted">
              {byAccount.map((row) => (
                <li key={row.account_id} className="flex justify-between gap-3">
                  <span>
                    {row.name}
                    <span className="text-slate-500"> · {row.subtype}</span>
                  </span>
                  <span className="text-slate-200">{formatMoney(row.ytd_contributions)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11px] text-slate-500">
            Roth and brokerage contributions come from Plaid. Enter totals on Accounts for 401(k)
            and HSA.
          </p>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-muted">
            <span>Safety net ({goals.safety_net.pct_of_income}% of income)</span>
            <span>
              {formatMoney(goals.safety_net.current_balance)} / {formatMoney(goals.safety_net.target_balance)}
            </span>
          </div>
          <ProgressBar pct={safetyPct} />
        </div>
      </div>
    </Card>
  );
}
