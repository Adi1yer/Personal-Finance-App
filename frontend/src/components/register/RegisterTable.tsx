import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import {
  api,
  formatMoney,
  type Category,
  type RegisterRow,
} from "../../api/client";
import { Badge } from "../ui";
import { cn } from "../../lib/utils";
import NewCategoryPopover from "./NewCategoryPopover";
import CategorySelect from "./CategorySelect";

type Props = {
  rows: RegisterRow[];
  openingBalance: string;
  searchActive: boolean;
  accountSubtype: string;
  balanceColumnLabel: string;
  categories: Category[];
  accountId: number;
  amountOutLabel: string;
  amountInLabel: string;
  focusedEntryId: number | null;
  onFocusEntry: (id: number | null) => void;
  clearedBalance: string;
  unclearedBalance: string;
  filter: "all" | "uncleared";
};

function isEnhancedRegisterSubtype(subtype: string): boolean {
  return ["brokerage", "retirement", "hsa", "credit_card"].includes(subtype);
}

function isInvestmentSubtype(subtype: string): boolean {
  return ["brokerage", "retirement", "hsa"].includes(subtype);
}

function activityBadgeTone(label: string | null): "amber" | "green" | "blue" | "neutral" {
  if (!label) return "neutral";
  const lower = label.toLowerCase();
  if (
    lower.includes("purchase") ||
    lower.includes("reinvest") ||
    lower.includes("withdrawal") ||
    lower.includes("interest charge") ||
    lower.includes("annual fee") ||
    lower.includes("late fee")
  ) {
    return "amber";
  }
  if (
    lower.includes("sale") ||
    lower.includes("dividend") ||
    lower.includes("contribution") ||
    lower.includes("interest") ||
    lower.includes("distribution") ||
    lower.includes("payment") ||
    lower.includes("refund")
  ) {
    return "green";
  }
  return "blue";
}

function outflowTooltip(label: string | null, accountSubtype: string): string {
  if (label?.toLowerCase().includes("purchase")) {
    return accountSubtype === "credit_card"
      ? "Charge on your card"
      : "Cash used to buy shares";
  }
  if (label?.toLowerCase().includes("reinvest")) return "Dividend reinvested into shares";
  if (label?.toLowerCase().includes("contribution")) return "Money contributed to account";
  if (label?.toLowerCase().includes("interest charge")) return "Interest charged on balance";
  if (label?.toLowerCase().includes("annual fee")) return "Annual card fee";
  return accountSubtype === "credit_card" ? "Charge on your card" : "Cash leaving the account";
}

function inflowTooltip(label: string | null, accountSubtype: string): string {
  if (label?.toLowerCase().includes("dividend")) return "Cash received from dividend";
  if (label?.toLowerCase().includes("sale")) return "Cash received from sale";
  if (label?.toLowerCase().includes("distribution")) return "Cash distributed from account";
  if (label?.toLowerCase().includes("payment")) return "Payment toward card balance";
  if (label?.toLowerCase().includes("refund")) return "Refund credited to card";
  return accountSubtype === "credit_card" ? "Payment or credit on card" : "Cash entering the account";
}

function ruleAmountDirection(row: RegisterRow): "any" | "outflow" | "inflow" {
  if (row.charge) return "outflow";
  if (row.payment) return "inflow";
  return "any";
}

function ConflictDot({ title }: { title: string }) {
  return (
    <span
      className="inline-block h-3 w-3 shrink-0 rounded-full bg-amber-400"
      title={title}
    />
  );
}

function ClearedDot({
  cleared,
  onClick,
}: {
  cleared: boolean;
  onClick: (e: MouseEvent) => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={cleared ? "Cleared" : "Mark cleared (Cmd+Enter)"}
      className={cn(
        "h-3 w-3 rounded-full border-2 transition-colors",
        cleared
          ? "border-positive bg-positive"
          : "border-slate-500 bg-transparent hover:border-slate-300"
      )}
    />
  );
}

export default function RegisterTable({
  rows,
  openingBalance,
  searchActive,
  accountSubtype,
  balanceColumnLabel,
  categories,
  accountId,
  amountOutLabel,
  amountInLabel,
  focusedEntryId,
  onFocusEntry,
  clearedBalance,
  unclearedBalance,
  filter,
}: Props) {
  const isInvestment = isInvestmentSubtype(accountSubtype);
  const isEnhancedRegister = isEnhancedRegisterSubtype(accountSubtype);
  const qc = useQueryClient();
  const [newCategoryRowId, setNewCategoryRowId] = useState<number | null>(null);
  const [rememberPrompt, setRememberPrompt] = useState<{
    entryId: number;
    pattern: string;
    amountDirection: "any" | "outflow" | "inflow";
    categoryId: number;
    categoryName: string;
  } | null>(null);

  const patchEntry = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { category_id?: number | null; is_cleared?: boolean } }) =>
      api.patchEntry(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["register", accountId] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const createRule = useMutation({
    mutationFn: api.createCategoryRule,
    onSuccess: () => {
      setRememberPrompt(null);
      qc.invalidateQueries({ queryKey: ["register", accountId] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const toggleCleared = useCallback(
    (row: RegisterRow) => {
      patchEntry.mutate({ id: row.entry_id, body: { is_cleared: !row.is_cleared } });
    },
    [patchEntry]
  );

  const expenseCategories = categories.filter((c) => c.category_type === "expense");
  const incomeCategories = categories.filter((c) => c.category_type === "income");

  const filteredBalances = useMemo(() => {
    if (!searchActive) return null;
    const sorted = [...rows].sort((a, b) => {
      if (a.txn_date !== b.txn_date) return a.txn_date.localeCompare(b.txn_date);
      return a.entry_id - b.entry_id;
    });
    let running = Number(openingBalance);
    const map = new Map<number, number>();
    for (const row of sorted) {
      const charge = row.charge ? Number(row.charge) : 0;
      const payment = row.payment ? Number(row.payment) : 0;
      running += payment - charge;
      map.set(row.entry_id, running);
    }
    return map;
  }, [searchActive, rows, openingBalance]);

  const displayRows = useMemo(() => [...rows].reverse(), [rows]);

  const markClearedAndAdvance = useCallback(
    (row: RegisterRow) => {
      const idx = displayRows.findIndex((r) => r.entry_id === row.entry_id);
      const nextRow =
        idx >= 0 && idx < displayRows.length - 1 ? displayRows[idx + 1] : null;

      const advance = () => onFocusEntry(nextRow?.entry_id ?? null);

      if (row.is_cleared) {
        advance();
        return;
      }

      patchEntry.mutate(
        { id: row.entry_id, body: { is_cleared: true } },
        { onSuccess: advance }
      );
    },
    [displayRows, onFocusEntry, patchEntry]
  );

  const onCategoryChange = (
    row: RegisterRow,
    categoryId: number,
    categoryName?: string
  ) => {
    patchEntry.mutate({ id: row.entry_id, body: { category_id: categoryId } });
    if (row.payee && row.category_id !== categoryId) {
      const resolvedName =
        categoryName ?? categories.find((c) => c.id === categoryId)?.name ?? "Unknown";
      setRememberPrompt({
        entryId: row.entry_id,
        pattern: row.remember_pattern ?? row.payee,
        amountDirection: ruleAmountDirection(row),
        categoryId,
        categoryName: resolvedName,
      });
    }
  };

  const applySuggestion = (row: RegisterRow, categoryId: number) => {
    patchEntry.mutate({ id: row.entry_id, body: { category_id: categoryId } });
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key !== "Enter") return;
      if (focusedEntryId == null) return;
      const row = displayRows.find((r) => r.entry_id === focusedEntryId);
      if (row) {
        e.preventDefault();
        markClearedAndAdvance(row);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [focusedEntryId, displayRows, markClearedAndAdvance]);

  useEffect(() => {
    if (focusedEntryId == null) return;
    if (!displayRows.some((r) => r.entry_id === focusedEntryId)) {
      onFocusEntry(null);
    }
  }, [displayRows, focusedEntryId, onFocusEntry]);

  const emptyMessage =
    filter === "uncleared"
      ? "All transactions are cleared."
      : searchActive
        ? "No transactions match your search."
        : "No transactions in this period. Sync from Plaid or add a manual entry.";

  if (rows.length === 0) {
    return (
      <div>
        <p className="px-5 py-12 text-center text-sm text-muted">{emptyMessage}</p>
        <RegisterFooter
          clearedBalance={clearedBalance}
          unclearedBalance={unclearedBalance}
          onClearFocus={() => onFocusEntry(null)}
        />
      </div>
    );
  }

  return (
    <div className="relative flex min-h-full flex-col">
      <table className="w-full text-left text-sm">
        <thead
          className="sticky top-0 z-[1] bg-surface-raised"
          onClick={() => onFocusEntry(null)}
        >
          <tr className="border-b border-surface-border text-[10px] uppercase tracking-wide text-muted">
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Description</th>
            <th className="w-10 px-2 py-3 text-center font-medium">C</th>
            <th className="px-4 py-3 font-medium">Category</th>
            <th className="w-6 px-1 py-3" aria-label="Category conflict" />
            <th className="px-4 py-3 text-right font-medium" title={isInvestment ? "Cash spent on purchases or reinvestments" : undefined}>
              {amountOutLabel}
            </th>
            <th className="px-4 py-3 text-right font-medium" title={isInvestment ? "Cash received from sales, dividends, or distributions" : undefined}>
              {amountInLabel}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {searchActive ? `${balanceColumnLabel} (filtered)` : balanceColumnLabel}
            </th>
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row) => {
            const displayBalance = filteredBalances?.get(row.entry_id) ?? Number(row.running_balance);
            const showSuggestions =
              focusedEntryId === row.entry_id &&
              !row.category_id &&
              row.category_suggestions.length > 1;

            return (
              <tr
                key={row.entry_id}
                data-register-row=""
                onClick={() => onFocusEntry(row.entry_id)}
                className={cn(
                  "cursor-pointer border-b border-surface-border/50 outline-none transition-colors",
                  focusedEntryId === row.entry_id
                    ? "bg-accent/15 ring-1 ring-inset ring-accent/50"
                    : "hover:bg-surface-overlay/30",
                  !row.is_cleared && focusedEntryId !== row.entry_id && "bg-surface-overlay/10"
                )}
              >
                <td className="whitespace-nowrap px-4 py-2.5 align-top text-slate-400">
                  {row.txn_date}
                </td>
                <td className="max-w-xs px-4 py-2.5 align-top">
                  <div className="font-medium text-white">{row.payee || "—"}</div>
                  {row.memo && (
                    <div className="mt-0.5 truncate text-xs text-muted">{row.memo}</div>
                  )}
                  {row.activity_label && isEnhancedRegister && (
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge tone={activityBadgeTone(row.activity_label)}>
                        {row.activity_label}
                      </Badge>
                      {row.security_name && (
                        <span className="text-xs text-slate-400">{row.security_name}</span>
                      )}
                      {row.quantity && (
                        <span className="text-xs text-muted">
                          {row.quantity} @ {row.price ? formatMoney(row.price) : "—"}
                        </span>
                      )}
                    </div>
                  )}
                  {row.investment_type && !isInvestment && (
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge tone="blue">
                        {row.investment_type}
                        {row.investment_subtype ? ` / ${row.investment_subtype}` : ""}
                      </Badge>
                      {row.security_name && (
                        <span className="text-xs text-slate-400">{row.security_name}</span>
                      )}
                      {row.quantity && (
                        <span className="text-xs text-muted">
                          {row.quantity} @ {row.price ? formatMoney(row.price) : "—"}
                        </span>
                      )}
                    </div>
                  )}
                  {row.is_transfer && <Badge tone="neutral">Transfer</Badge>}
                </td>
                <td className="px-2 py-2.5 text-center align-top">
                  <ClearedDot
                    cleared={row.is_cleared}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleCleared(row);
                    }}
                  />
                </td>
                <td className="relative px-4 py-2 align-top">
                  <CategorySelect
                    value={row.category_id}
                    expenseCategories={expenseCategories}
                    incomeCategories={incomeCategories}
                    accountId={accountId}
                    onChange={(categoryId) => {
                      if (categoryId == null) {
                        patchEntry.mutate({ id: row.entry_id, body: { category_id: null } });
                        return;
                      }
                      onCategoryChange(row, categoryId);
                    }}
                    onCreateNew={() => setNewCategoryRowId(row.entry_id)}
                  />
                  {showSuggestions && (
                    <div className="absolute left-0 top-full z-20 mt-1 w-72 rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-xs shadow-xl">
                      <p className="mb-2 text-[10px] uppercase tracking-wide text-muted">
                        Choose a category
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {row.category_suggestions.map((suggestion, index) => (
                          <button
                            key={`${suggestion.category_id}-${suggestion.rule_id ?? index}`}
                            type="button"
                            className="rounded-full border border-surface-border bg-surface-overlay px-2.5 py-1 text-left text-white hover:border-accent hover:bg-accent/20"
                            title={suggestion.label ?? undefined}
                            onClick={(e) => {
                              e.stopPropagation();
                              applySuggestion(row, suggestion.category_id);
                            }}
                          >
                            {index + 1}. {suggestion.category_name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {newCategoryRowId === row.entry_id && (
                    <NewCategoryPopover
                      onCreated={(id, name) => onCategoryChange(row, id, name)}
                      onClose={() => setNewCategoryRowId(null)}
                    />
                  )}
                  {rememberPrompt?.entryId === row.entry_id && (
                    <div className="absolute left-0 top-full z-20 mt-1 w-72 rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-xs shadow-xl">
                      <p className="text-slate-300">
                        Remember &quot;{rememberPrompt.pattern}&quot; → &quot;
                        {rememberPrompt.categoryName}&quot;?
                      </p>
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          className="rounded bg-accent px-2 py-1 text-white"
                          onClick={(e) => {
                            e.stopPropagation();
                            createRule.mutate({
                              pattern: rememberPrompt.pattern,
                              category_id: rememberPrompt.categoryId,
                              amount_direction: rememberPrompt.amountDirection,
                            });
                          }}
                        >
                          Yes
                        </button>
                        <button
                          type="button"
                          className="text-muted hover:text-white"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRememberPrompt(null);
                          }}
                        >
                          No
                        </button>
                      </div>
                    </div>
                  )}
                </td>
                <td className="px-1 py-2.5 text-center align-top">
                  {row.category_conflict ? (
                    <ConflictDot title="Similar transactions use different categories" />
                  ) : null}
                </td>
                <td
                  className="whitespace-nowrap px-4 py-2.5 text-right align-top tabular-nums text-negative"
                  title={row.charge ? outflowTooltip(row.activity_label, accountSubtype) : undefined}
                >
                  {row.charge ? (
                    <span className="inline-flex items-center justify-end gap-1">
                      {isEnhancedRegister && <ArrowDownLeft className="h-3 w-3 shrink-0 opacity-70" />}
                      {formatMoney(row.charge)}
                    </span>
                  ) : (
                    ""
                  )}
                </td>
                <td
                  className="whitespace-nowrap px-4 py-2.5 text-right align-top tabular-nums text-positive"
                  title={row.payment ? inflowTooltip(row.activity_label, accountSubtype) : undefined}
                >
                  {row.payment ? (
                    <span className="inline-flex items-center justify-end gap-1">
                      {isEnhancedRegister && <ArrowUpRight className="h-3 w-3 shrink-0 opacity-70" />}
                      {formatMoney(row.payment)}
                    </span>
                  ) : (
                    ""
                  )}
                </td>
                <td
                  className={cn(
                    "whitespace-nowrap px-4 py-2.5 text-right align-top tabular-nums font-medium",
                    displayBalance < 0 ? "text-negative" : "text-white"
                  )}
                >
                  {formatMoney(String(displayBalance))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <RegisterFooter
        clearedBalance={clearedBalance}
        unclearedBalance={unclearedBalance}
        onClearFocus={() => onFocusEntry(null)}
      />
    </div>
  );
}

function RegisterFooter({
  clearedBalance,
  unclearedBalance,
  onClearFocus,
}: {
  clearedBalance: string;
  unclearedBalance: string;
  onClearFocus: () => void;
}) {
  return (
    <div
      className="sticky bottom-0 mt-auto flex items-center justify-end gap-6 border-t border-surface-border bg-surface-raised px-6 py-3 text-xs"
      onClick={onClearFocus}
    >
      <span className="text-muted">
        Cleared:{" "}
        <span className="font-medium tabular-nums text-white">
          {formatMoney(clearedBalance)}
        </span>
      </span>
      <span className="text-muted">
        Uncleared:{" "}
        <span className="font-medium tabular-nums text-white">
          {formatMoney(unclearedBalance)}
        </span>
      </span>
    </div>
  );
}
