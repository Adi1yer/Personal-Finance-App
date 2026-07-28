import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Wallet,
  List,
  Scale,
  BarChart3,
  Settings,
  Target,
  Bot,
  GitCompare,
  ListFilter,
} from "lucide-react";
import { cn } from "../lib/utils";

const links = [
  { to: "/", icon: LayoutDashboard, label: "Overview", end: true },
  { to: "/accounts", icon: Wallet, label: "Accounts" },
  { to: "/register", icon: List, label: "Register" },
  { to: "/goals", icon: Target, label: "Goals" },
  { to: "/advisor", icon: Bot, label: "Advisor" },
  { to: "/review/duplicates", icon: GitCompare, label: "Duplicates" },
  { to: "/rules", icon: ListFilter, label: "Rules" },
  { to: "/reconcile", icon: Scale, label: "Reconcile" },
  { to: "/reports", icon: BarChart3, label: "Reports" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-surface-border bg-surface-raised">
      <div className="drag-region flex h-12 items-center gap-2 border-b border-surface-border px-5 pt-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/20 text-accent">
          <Wallet className="h-4 w-4" />
        </div>
        <span className="no-drag text-sm font-semibold text-white">Personal Finance</span>
      </div>
      <nav className="no-drag flex flex-1 flex-col gap-0.5 p-3">
        {links.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                isActive
                  ? "bg-accent-soft font-medium text-accent"
                  : "text-muted hover:bg-surface-overlay hover:text-slate-200"
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="no-drag border-t border-surface-border p-4 text-[10px] text-muted">
        Local ledger · your data stays on this Mac
      </div>
    </aside>
  );
}
