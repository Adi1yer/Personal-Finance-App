import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, formatMoney } from "../api/client";
import GoalProgressWidget from "../components/goals/GoalProgressWidget";
import { Card, CardHeader } from "../components/ui";

export default function GoalsPage() {
  const [years, setYears] = useState(20);
  const [appreciation, setAppreciation] = useState(7);
  const [divGrowth, setDivGrowth] = useState(3);

  const goals = useQuery({ queryKey: ["goalsProgress"], queryFn: api.goalsProgress });
  const projection = useQuery({
    queryKey: ["projections", years, appreciation, divGrowth],
    queryFn: () =>
      api.projections({
        horizon_years: years,
        stock_appreciation_pct: appreciation,
        dividend_growth_pct: divGrowth,
      }),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-lg font-semibold text-white">Goals & projections</h1>

      {goals.data && <GoalProgressWidget goals={goals.data} />}

      <Card>
        <CardHeader title="Projection assumptions" />
        <div className="grid gap-4 p-4 sm:grid-cols-3">
          <label className="text-xs text-muted">
            Years: {years}
            <input
              type="range"
              min={5}
              max={40}
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </label>
          <label className="text-xs text-muted">
            Appreciation: {appreciation}%
            <input
              type="range"
              min={0}
              max={15}
              step={0.5}
              value={appreciation}
              onChange={(e) => setAppreciation(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </label>
          <label className="text-xs text-muted">
            Dividend growth: {divGrowth}%
            <input
              type="range"
              min={0}
              max={10}
              step={0.5}
              value={divGrowth}
              onChange={(e) => setDivGrowth(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </label>
        </div>
      </Card>

      {projection.data && (
        <Card>
          <CardHeader title={`In ${years} years`} />
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted">Portfolio value</p>
              <p className="text-xl font-semibold text-white">
                {formatMoney(projection.data.projected_final.portfolio_value)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Annual dividend income</p>
              <p className="text-xl font-semibold text-emerald-400">
                {formatMoney(projection.data.projected_final.annual_dividend_income)}
              </p>
              <p className="text-xs text-muted">
                {formatMoney(projection.data.projected_final.monthly_dividend_income)}/mo
              </p>
            </div>
          </div>
          <div className="max-h-48 overflow-auto border-t border-surface-border p-4 text-xs">
            {projection.data.series.map((pt) => (
              <div key={String(pt.year)} className="flex justify-between py-0.5 text-muted">
                <span>Year {pt.year}</span>
                <span>{formatMoney(String(pt.portfolio_value))}</span>
                <span className="text-emerald-400/80">{formatMoney(String(pt.annual_dividend_income))}/yr</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
