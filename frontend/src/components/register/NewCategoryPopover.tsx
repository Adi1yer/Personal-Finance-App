import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { Button, Input } from "../ui";

type Props = {
  onCreated: (categoryId: number, categoryName: string) => void;
  onClose: () => void;
};

export default function NewCategoryPopover({ onCreated, onClose }: Props) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<"expense" | "income">("expense");
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: () => api.createCategory({ name: name.trim(), category_type: type }),
    onSuccess: (cat) => {
      qc.invalidateQueries({ queryKey: ["categories"] });
      onCreated(cat.id, cat.name);
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="absolute right-0 top-full z-20 mt-1 w-64 rounded-lg border border-surface-border bg-surface-raised p-3 shadow-xl">
      <p className="text-xs font-medium text-white">New category</p>
      <div className="mt-2 space-y-2">
        <Input
          placeholder="Category name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value as "expense" | "income")}
          className="w-full rounded-lg border border-surface-border bg-surface-overlay px-3 py-2 text-xs text-white"
        >
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </select>
        {error && <p className="text-xs text-negative">{error}</p>}
        <div className="flex gap-2">
          <Button
            size="sm"
            className="flex-1"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Add
          </Button>
          <Button size="sm" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
