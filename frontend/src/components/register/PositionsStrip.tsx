import { formatMoney, type HoldingSummary } from "../../api/client";
import { cn } from "../../lib/utils";

type Props = {
  holdings: HoldingSummary[];
  cashBalance: string | null;
  asOfDate: string | null;
};

export default function PositionsStrip({ holdings, cashBalance, asOfDate }: Props) {
  const cash = cashBalance ? Number(cashBalance) : 0;

  return (
    <div className="border-b border-surface-border bg-surface-overlay/20 px-6 py-3">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <p className="text-[10px] uppercase tracking-wide text-muted">Positions</p>
        {asOfDate && (
          <p className="text-[10px] text-muted">
            Prices as of{" "}
            {new Date(`${asOfDate}T12:00:00`).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-muted">
              <th className="pb-1.5 pr-4 font-medium">Security</th>
              <th className="pb-1.5 pr-4 text-right font-medium">Qty</th>
              <th className="pb-1.5 pr-4 text-right font-medium">Cost</th>
              <th className="pb-1.5 pr-4 text-right font-medium">Value</th>
              <th className="pb-1.5 text-right font-medium">Gain</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => {
              const gain = Number(h.gain);
              return (
                <tr key={h.ticker} className="border-t border-surface-border/40">
                  <td className="py-1.5 pr-4">
                    <span className="font-medium text-white">{h.ticker}</span>
                    <span className="ml-2 truncate text-muted">{h.security_name}</span>
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums text-slate-300">
                    {Number(h.quantity).toLocaleString(undefined, { maximumFractionDigits: 5 })}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums text-slate-300">
                    {formatMoney(h.cost_basis_total)}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums text-white">
                    {formatMoney(h.market_value)}
                  </td>
                  <td
                    className={cn(
                      "py-1.5 text-right tabular-nums font-medium",
                      gain >= 0 ? "text-positive" : "text-negative"
                    )}
                  >
                    {gain >= 0 ? "+" : ""}
                    {formatMoney(h.gain)}
                  </td>
                </tr>
              );
            })}
            {cash > 0 && (
              <tr className="border-t border-surface-border/40">
                <td className="py-1.5 pr-4 font-medium text-white">Cash sweep</td>
                <td className="py-1.5 pr-4" />
                <td className="py-1.5 pr-4" />
                <td className="py-1.5 pr-4 text-right tabular-nums text-white">
                  {formatMoney(cashBalance!)}
                </td>
                <td className="py-1.5" />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
