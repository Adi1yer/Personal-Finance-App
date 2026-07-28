import { Link } from "react-router-dom";
import { List, Scale, Pencil } from "lucide-react";
import { formatMoney, type OverviewAccountLine } from "../../api/client";
import { Badge, Button, Card } from "../ui";

type Props = {
  account: OverviewAccountLine;
};

export default function AccountDetail({ account }: Props) {
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">{account.name}</h2>
          <div className="mt-2 flex items-center gap-2">
            <Badge tone={account.sync_source === "plaid" ? "blue" : "neutral"}>
              {account.sync_source}
            </Badge>
            <span className="text-xs text-muted">{account.subtype.replace("_", " ")}</span>
            <span className="text-xs text-muted">· {account.last_updated_label}</span>
          </div>
        </div>
        <p className="text-3xl font-semibold tabular-nums text-white">
          {formatMoney(account.balance)}
        </p>
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        <Link to={`/register?account=${account.id}`}>
          <Button size="sm" className="gap-2">
            <List className="h-4 w-4" />
            Register
          </Button>
        </Link>
        <Link to={`/reconcile?account=${account.id}`}>
          <Button size="sm" variant="secondary" className="gap-2">
            <Scale className="h-4 w-4" />
            Reconcile
          </Button>
        </Link>
        <Link to="/accounts">
          <Button size="sm" variant="secondary" className="gap-2">
            <Pencil className="h-4 w-4" />
            Edit accounts
          </Button>
        </Link>
      </div>
    </Card>
  );
}
