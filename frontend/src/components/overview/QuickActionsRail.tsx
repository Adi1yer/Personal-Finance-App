import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, Plus, RefreshCw, Settings } from "lucide-react";
import { api, type SyncHealth } from "../../api/client";
import { formatPlaidSyncSummary } from "../../lib/plaidSync";
import { Button, Card, CardHeader } from "../ui";

type Props = {
  plaidReady: boolean;
  onSyncDone?: (msg: string) => void;
  onHealth?: (health: SyncHealth | null) => void;
};

export default function QuickActionsRail({ plaidReady, onSyncDone, onHealth }: Props) {
  const qc = useQueryClient();
  const [syncMsg, setSyncMsg] = useState("");

  const sync = useMutation({
    mutationFn: api.plaidSync,
    onSuccess: (data) => {
      const msg = formatPlaidSyncSummary(data);
      setSyncMsg(msg);
      onSyncDone?.(msg);
      onHealth?.(data.health ?? null);
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
      qc.invalidateQueries({ queryKey: ["netWorthHistory"] });
    },
    onError: (e) => setSyncMsg((e as Error).message),
  });

  return (
    <Card className="h-fit">
      <CardHeader title="Quick actions" />
      <div className="space-y-2 p-4">
        <Link to="/settings" className="block">
          <Button variant="secondary" size="sm" className="w-full justify-start gap-2">
            <Link2 className="h-4 w-4" />
            Connect bank
          </Button>
        </Link>
        <Button
          variant="secondary"
          size="sm"
          className="w-full justify-start gap-2"
          disabled={!plaidReady || sync.isPending}
          onClick={() => sync.mutate()}
        >
          <RefreshCw className={`h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} />
          Sync now
        </Button>
        <Link to="/accounts" className="block">
          <Button variant="secondary" size="sm" className="w-full justify-start gap-2">
            <Plus className="h-4 w-4" />
            Add account
          </Button>
        </Link>
        <Link to="/settings" className="block">
          <Button variant="ghost" size="sm" className="w-full justify-start gap-2">
            <Settings className="h-4 w-4" />
            Settings
          </Button>
        </Link>
        {syncMsg && <p className="text-[10px] text-muted">{syncMsg}</p>}
      </div>
    </Card>
  );
}
