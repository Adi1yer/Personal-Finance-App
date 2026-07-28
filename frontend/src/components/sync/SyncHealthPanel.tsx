import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { type SyncHealth } from "../../api/client";
import { Card, CardHeader } from "../ui";

type Props = {
  health: SyncHealth | null | undefined;
  insights?: string[];
};

export default function SyncHealthPanel({ health, insights }: Props) {
  if (!health) return null;

  return (
    <Card>
      <CardHeader
        title="Sync health"
        action={
          health.ok ? (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" /> Healthy
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5" /> Needs attention
            </span>
          )
        }
      />
      <div className="space-y-2 p-4 text-xs text-slate-300">
        {health.warnings.map((w) => (
          <p key={w} className="text-amber-300/90">
            {w}
          </p>
        ))}
        <div className="grid grid-cols-2 gap-2 text-muted">
          <span>Posted: {health.sync.posted as number}</span>
          <span>Holdings: {health.sync.holdings_updated as number}</span>
          <span>Dupes repaired: {health.sync.plaid_duplicate_repair as number}</span>
          <span>Staging pending: {health.staging_pending}</span>
        </div>
        {health.suspected_duplicate_clusters > 0 && (
          <Link to="/review/duplicates" className="text-accent hover:underline">
            Review {health.suspected_duplicate_clusters} duplicate cluster(s) →
          </Link>
        )}
        {insights && insights.length > 0 && (
          <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-400">
            {insights.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
