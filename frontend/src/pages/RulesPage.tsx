import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CategoryRule } from "../api/client";
import { Button, Card, CardHeader, Input, Select } from "../components/ui";

export default function RulesPage() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["categoryRules"], queryFn: api.categoryRules });
  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const [draft, setDraft] = useState({ pattern: "", category_id: "", priority: "10" });

  const create = useMutation({
    mutationFn: () =>
      api.createCategoryRule({
        pattern: draft.pattern,
        category_id: Number(draft.category_id),
        priority: Number(draft.priority),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["categoryRules"] });
      setDraft({ pattern: "", category_id: "", priority: "10" });
    },
  });

  const reapply = useMutation({
    mutationFn: () => api.reapplyCategoryRules(90),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteCategoryRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["categoryRules"] }),
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-white">Category rules</h1>
        <Button size="sm" variant="secondary" onClick={() => reapply.mutate()} disabled={reapply.isPending}>
          Re-apply to last 90 days
        </Button>
      </div>

      <Card>
        <CardHeader title="New rule" />
        <div className="flex flex-wrap gap-2 p-4">
          <Input
            placeholder="Payee pattern"
            value={draft.pattern}
            onChange={(e) => setDraft({ ...draft, pattern: e.target.value })}
            className="min-w-[200px] flex-1"
          />
          <Select
            value={draft.category_id}
            onChange={(e) => setDraft({ ...draft, category_id: e.target.value })}
          >
            <option value="">Category</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Button size="sm" onClick={() => create.mutate()} disabled={!draft.pattern || !draft.category_id}>
            Add
          </Button>
        </div>
      </Card>

      <div className="space-y-2">
        {rules.data?.map((rule: CategoryRule) => (
          <Card key={rule.id}>
            <div className="flex items-center justify-between p-4 text-sm">
              <div>
                <p className="font-medium text-white">{rule.pattern}</p>
                <p className="text-xs text-muted">
                  {rule.category_name ?? rule.category_id} · priority {rule.priority} · {rule.amount_direction}
                </p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => remove.mutate(rule.id)}>
                Delete
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
