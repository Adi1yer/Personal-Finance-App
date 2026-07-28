import React from "react";
import { cn } from "../lib/utils";
import { ChevronDown } from "lucide-react";

export function Card({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-surface-border bg-surface-raised shadow-card",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-surface-border px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatCard({
  label,
  value,
  trend,
  variant = "default",
}: {
  label: string;
  value: string;
  trend?: string;
  variant?: "default" | "positive" | "negative";
}) {
  const valueColor =
    variant === "positive"
      ? "text-positive"
      : variant === "negative"
        ? "text-negative"
        : "text-white";

  return (
    <Card className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={cn("mt-2 text-2xl font-semibold tabular-nums", valueColor)}>{value}</p>
      {trend && <p className="mt-1 text-xs text-muted">{trend}</p>}
    </Card>
  );
}

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
}) {
  return (
    <button
      className={cn(
        "no-drag inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50",
        size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm",
        variant === "primary" && "bg-accent text-white hover:bg-accent-muted",
        variant === "secondary" &&
          "border border-surface-border bg-surface-overlay text-slate-200 hover:bg-surface-border",
        variant === "ghost" && "text-muted hover:bg-surface-overlay hover:text-white",
        className
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <select
        className={cn(
          "no-drag w-full appearance-none rounded-lg border border-surface-border",
          "bg-surface-overlay px-3 py-2.5 pr-9 text-sm text-white",
          "outline-none transition-colors",
          "focus:border-accent focus:ring-1 focus:ring-accent/30",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "[color-scheme:dark]"
        )}
        {...props}
      />
      <ChevronDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        aria-hidden
      />
    </div>
  );
}

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      className={cn(
        "no-drag w-full rounded-lg border border-surface-border bg-surface-overlay px-3 py-2.5 text-sm text-white",
        "outline-none transition-colors placeholder:text-muted",
        "focus:border-accent focus:ring-1 focus:ring-accent/30",
        "[color-scheme:dark]",
        className
      )}
      {...props}
    />
  );
});

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "blue" | "green" | "amber";
}) {
  const tones = {
    neutral: "bg-surface-overlay text-muted",
    blue: "bg-accent-soft text-accent",
    green: "bg-positive/10 text-positive",
    amber: "bg-amber-500/10 text-amber-400",
  };
  return (
    <span
      className={cn(
        "inline-flex rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
        tones[tone]
      )}
    >
      {children}
    </span>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <p className="text-sm font-medium text-slate-300">{title}</p>
      <p className="mt-1 max-w-sm text-xs text-muted">{description}</p>
    </div>
  );
}
