import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatMoney, type DuplicateCluster } from "../api/client";
import { Button, Card, CardHeader } from "../components/ui";

function ClusterCard({ cluster }: { cluster: DuplicateCluster }) {
  const qc = useQueryClient();
  const [keepId, setKeepId] = useState(cluster.transactions[0]?.transaction_id);

  const merge = useMutation({
    mutationFn: () => api.mergeDuplicate(cluster.id, keepId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["duplicates"] }),
  });
  const keepBoth = useMutation({
    mutationFn: () => api.keepBothDuplicates(cluster.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["duplicates"] }),
  });

  return (
    <Card>
      <CardHeader
        title={`${cluster.account_name} · ${formatMoney(cluster.amount)}`}
        action={<span className="text-xs text-muted">{cluster.confidence}</span>}
      />
      <div className="space-y-3 p-4 text-sm">
        <p className="text-xs text-muted">{cluster.payee_key} · {cluster.reasons.join(", ")}</p>
        <div className="space-y-2">
          {cluster.transactions.map((t) => (
            <label key={t.transaction_id} className="flex cursor-pointer items-center gap-2 rounded border border-surface-border p-2">
              <input
                type="radio"
                name={`keep-${cluster.id}`}
                checked={keepId === t.transaction_id}
                onChange={() => setKeepId(t.transaction_id)}
              />
              <span>
                {t.txn_date} · {t.payee} · {formatMoney(t.amount)}
                {t.is_cleared ? " · cleared" : " · pending"}
              </span>
            </label>
          ))}
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => merge.mutate()} disabled={merge.isPending}>
            Merge (keep selected)
          </Button>
          <Button size="sm" variant="secondary" onClick={() => keepBoth.mutate()}>
            Keep both
          </Button>
        </div>
      </div>
    </Card>
  );
}

export default function DuplicatesPage() {
  const dupes = useQuery({ queryKey: ["duplicates"], queryFn: api.duplicates });

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-lg font-semibold text-white">Duplicate review</h1>
      <p className="text-sm text-muted">Same payee and amount within 7 days — merge or keep both.</p>
      {dupes.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {dupes.data?.length === 0 && (
        <p className="text-sm text-emerald-400">No suspected duplicates.</p>
      )}
      {dupes.data?.map((c) => (
        <ClusterCard key={c.id} cluster={c} />
      ))}
    </div>
  );
}
