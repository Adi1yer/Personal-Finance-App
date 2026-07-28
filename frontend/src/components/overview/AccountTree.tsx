import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { formatMoney, type OverviewGroup, type OverviewResponse } from "../../api/client";
import { Badge } from "../ui";
import { cn } from "../../lib/utils";

function RegisterStatusDot({ pendingCount }: { pendingCount: number }) {
  const pending = Number(pendingCount) || 0;
  const caughtUp = pending === 0;
  return (
    <span
      className={cn(
        "inline-block h-2.5 w-2.5 shrink-0 rounded-full",
        caughtUp ? "bg-positive" : "bg-danger"
      )}
      title={
        caughtUp
          ? "Register is caught up"
          : `${pending} uncleared item${pending === 1 ? "" : "s"} in register`
      }
    />
  );
}

type Props = {
  data: OverviewResponse;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
};

export default function AccountTree({ data, selectedId, onSelect }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggle = (key: string) =>
    setCollapsed((c) => ({ ...c, [key]: !c[key] }));

  return (
    <div className="flex h-full flex-col border-r border-surface-border bg-surface-raised">
      <div className="border-b border-surface-border px-4 py-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">Net worth</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-white">
          {formatMoney(data.net_worth)}
        </p>
        <p className="mt-1 text-xs text-muted">
          Assets {formatMoney(data.total_assets)} · Liabilities{" "}
          {formatMoney(data.total_liabilities)}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {data.groups.length === 0 && (
          <p className="px-4 py-6 text-xs text-muted">Add accounts to see them here.</p>
        )}
        {data.groups.map((group: OverviewGroup) => {
          const isCollapsed = collapsed[group.key];
          return (
            <div key={group.key} className="mb-1">
              <button
                type="button"
                onClick={() => toggle(group.key)}
                className="flex w-full items-center gap-1 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted hover:bg-surface-overlay/50"
              >
                {isCollapsed ? (
                  <ChevronRight className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
                <span className="flex-1">{group.label}</span>
                <span className="tabular-nums text-slate-300">{formatMoney(group.total)}</span>
              </button>
              {!isCollapsed &&
                group.accounts.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => onSelect(a.id)}
                    className={cn(
                      "flex w-full flex-col gap-0.5 px-4 py-2.5 text-left transition-colors",
                      selectedId === a.id
                        ? "bg-accent-soft"
                        : "hover:bg-surface-overlay/40"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <RegisterStatusDot pendingCount={a.register_pending_count ?? 0} />
                        <span className="truncate text-sm font-medium text-slate-200">{a.name}</span>
                      </div>
                      <span className="shrink-0 tabular-nums text-sm text-white">
                        {formatMoney(a.balance)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={a.sync_source === "plaid" ? "blue" : "neutral"}>
                        {a.sync_source}
                      </Badge>
                      <span className="text-[10px] text-muted">
                        {a.holdings_as_of
                          ? `As of ${a.holdings_as_of}`
                          : a.last_updated_label}
                      </span>
                    </div>
                  </button>
                ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
