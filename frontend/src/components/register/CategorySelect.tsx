import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type Category } from "../../api/client";
import { cn } from "../../lib/utils";
import { Button, Input } from "../ui";

type Props = {
  value: number | null;
  expenseCategories: Category[];
  incomeCategories: Category[];
  accountId: number;
  onChange: (categoryId: number | null) => void;
  onCreateNew: () => void;
};

const PROTECTED_CATEGORY_SLUGS = new Set([
  "groceries",
  "dining",
  "housing",
  "transportation",
  "utilities",
  "healthcare",
  "investment_contribution",
  "salary",
  "interest_dividends",
  "uncategorized",
]);

type FlyoutState = {
  category: Category;
  top: number;
  left: number;
};

type CategoryOptionProps = {
  category: Category;
  selected: boolean;
  onSelect: () => void;
  onOpenFlyout: (category: Category, anchor: HTMLElement) => void;
  onCloseFlyout: () => void;
  flyoutOpen: boolean;
};

function CategoryOption({
  category,
  selected,
  onSelect,
  onOpenFlyout,
  onCloseFlyout,
  flyoutOpen,
}: CategoryOptionProps) {
  const arrowRef = useRef<HTMLButtonElement>(null);

  return (
    <div
      className={cn(
        "flex items-center gap-0.5 rounded",
        selected && "bg-accent/20",
        flyoutOpen && "bg-surface-overlay/60"
      )}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
        className="min-w-0 flex-1 truncate rounded px-2 py-1.5 text-left text-xs text-white hover:bg-surface-overlay"
      >
        {category.name}
      </button>
      <button
        ref={arrowRef}
        type="button"
        title="Edit or delete category"
        onClick={(e) => e.stopPropagation()}
        onMouseEnter={() => {
          if (arrowRef.current) onOpenFlyout(category, arrowRef.current);
        }}
        onMouseLeave={onCloseFlyout}
        className={cn(
          "shrink-0 rounded p-1 text-muted hover:bg-surface-overlay hover:text-white",
          flyoutOpen && "bg-surface-overlay text-white"
        )}
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

type CategoryFlyoutProps = {
  flyout: FlyoutState;
  onCancelClose: () => void;
  onScheduleClose: () => void;
  onClose: () => void;
  onSave: (id: number, name: string, categoryType: "expense" | "income") => void;
  onDelete: (category: Category) => void;
  saving: boolean;
};

function CategoryFlyout({
  flyout,
  onCancelClose,
  onScheduleClose,
  onClose,
  onSave,
  onDelete,
  saving,
}: CategoryFlyoutProps) {
  const { category } = flyout;
  const protectedCat = PROTECTED_CATEGORY_SLUGS.has(category.slug);
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState(category.name);
  const [editType, setEditType] = useState<"expense" | "income">(
    category.category_type as "expense" | "income"
  );

  useEffect(() => {
    setEditName(category.name);
    setEditType(category.category_type as "expense" | "income");
    setEditOpen(false);
  }, [category.id, category.name, category.category_type]);

  const dirty =
    editName.trim() !== category.name ||
    editType !== (category.category_type as "expense" | "income");

  return createPortal(
    <div
      data-category-flyout=""
      className="fixed z-[100] flex items-start gap-1"
      style={{ top: flyout.top, left: flyout.left }}
      onMouseEnter={onCancelClose}
      onMouseLeave={() => {
        setEditOpen(false);
        onScheduleClose();
      }}
    >
      <div className="min-w-[88px] rounded-lg border border-surface-border bg-surface-raised py-1 shadow-2xl">
        <button
          type="button"
          className={cn(
            "flex w-full items-center justify-between px-3 py-1.5 text-left text-xs hover:bg-surface-overlay",
            editOpen ? "bg-surface-overlay text-white" : "text-white"
          )}
          onMouseEnter={() => setEditOpen(true)}
        >
          Edit
          <ChevronRight className="h-3 w-3 text-muted" />
        </button>
        {protectedCat ? (
          <p className="px-3 py-1.5 text-[10px] text-muted">Built-in</p>
        ) : (
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left text-xs text-negative hover:bg-surface-overlay"
            onClick={() => {
              onDelete(category);
              onClose();
            }}
          >
            Delete
          </button>
        )}
      </div>

      {editOpen && (
        <div className="w-52 rounded-lg border border-surface-border bg-surface-raised p-2 shadow-2xl">
          <p className="mb-2 text-[10px] uppercase tracking-wide text-muted">Edit category</p>
          <Input
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            autoFocus
            className="text-xs"
          />
          <select
            value={editType}
            onChange={(e) => setEditType(e.target.value as "expense" | "income")}
            className="mt-2 w-full rounded-lg border border-surface-border bg-surface-overlay px-2 py-1.5 text-xs text-white"
          >
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </select>
          <Button
            size="sm"
            className="mt-2 w-full"
            disabled={!editName.trim() || !dirty || saving}
            onClick={() => {
              onSave(category.id, editName.trim(), editType);
              onClose();
            }}
          >
            Save
          </Button>
        </div>
      )}
    </div>,
    document.body
  );
}

export default function CategorySelect({
  value,
  expenseCategories,
  incomeCategories,
  accountId,
  onChange,
  onCreateNew,
}: Props) {
  const qc = useQueryClient();
  const rootRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number>();
  const [open, setOpen] = useState(false);
  const [flyout, setFlyout] = useState<FlyoutState | null>(null);

  const selected =
    expenseCategories.find((c) => c.id === value) ??
    incomeCategories.find((c) => c.id === value);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["categories"] });
    qc.invalidateQueries({ queryKey: ["register", accountId] });
    qc.invalidateQueries({ queryKey: ["metrics"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };

  const updateCategory = useMutation({
    mutationFn: ({
      id,
      name,
      category_type,
    }: {
      id: number;
      name: string;
      category_type: "expense" | "income";
    }) => api.updateCategory(id, { name, category_type }),
    onSuccess: () => invalidate(),
  });

  const deleteCategory = useMutation({
    mutationFn: (id: number) => api.deleteCategory(id),
    onSuccess: (_data, deletedId) => {
      invalidate();
      if (value === deletedId) onChange(null);
    },
    onError: (e: Error) => window.alert(e.message),
  });

  const cancelCloseFlyout = useCallback(() => {
    window.clearTimeout(closeTimer.current);
  }, []);

  const scheduleCloseFlyout = useCallback(() => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setFlyout(null), 120);
  }, []);

  const closeFlyout = useCallback(() => {
    window.clearTimeout(closeTimer.current);
    setFlyout(null);
  }, []);

  const openFlyout = useCallback((category: Category, anchor: HTMLElement) => {
    cancelCloseFlyout();
    const rect = anchor.getBoundingClientRect();
    const panelHeight = 88;
    let top = rect.top;
    if (top + panelHeight > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - panelHeight - 8);
    }
    setFlyout({
      category,
      top,
      left: rect.right + 6,
    });
  }, [cancelCloseFlyout]);

  useEffect(() => {
    if (!open) {
      closeFlyout();
      return;
    }
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (rootRef.current?.contains(target)) return;
      if (target.closest("[data-category-flyout]")) return;
      setOpen(false);
      closeFlyout();
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, closeFlyout]);

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  const renderCategory = (category: Category) => (
    <CategoryOption
      key={category.id}
      category={category}
      selected={value === category.id}
      flyoutOpen={flyout?.category.id === category.id}
      onSelect={() => {
        onChange(category.id);
        setOpen(false);
        closeFlyout();
      }}
      onOpenFlyout={openFlyout}
      onCloseFlyout={scheduleCloseFlyout}
    />
  );

  return (
    <>
      <div ref={rootRef} className="relative max-w-[160px]" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded border border-surface-border bg-surface-overlay px-2 py-1 text-xs text-white"
        >
          <span className="truncate">{selected?.name ?? "—"}</span>
          <span className="ml-1 text-muted">▾</span>
        </button>
        {open && (
          <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-lg border border-surface-border bg-surface-raised p-1 shadow-xl">
            <div className="max-h-56 overflow-y-auto">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onChange(null);
                  setOpen(false);
                  closeFlyout();
                }}
                className="flex w-full rounded px-2 py-1.5 text-left text-xs text-muted hover:bg-surface-overlay hover:text-white"
              >
                —
              </button>
              {expenseCategories.length > 0 && (
                <div className="mt-1">
                  <p className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">Expense</p>
                  {expenseCategories.map(renderCategory)}
                </div>
              )}
              {incomeCategories.length > 0 && (
                <div className="mt-1">
                  <p className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">Income</p>
                  {incomeCategories.map(renderCategory)}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                closeFlyout();
                onCreateNew();
              }}
              className="mt-1 flex w-full rounded px-2 py-1.5 text-left text-xs text-accent hover:bg-surface-overlay"
            >
              + New category…
            </button>
          </div>
        )}
      </div>

      {flyout && (
        <CategoryFlyout
          flyout={flyout}
          onCancelClose={cancelCloseFlyout}
          onScheduleClose={scheduleCloseFlyout}
          onClose={closeFlyout}
          onSave={(id, name, category_type) =>
            updateCategory.mutate({ id, name, category_type })
          }
          onDelete={(cat) => {
            if (window.confirm(`Delete category "${cat.name}"?`)) {
              deleteCategory.mutate(cat.id);
            }
          }}
          saving={updateCategory.isPending}
        />
      )}
    </>
  );
}
