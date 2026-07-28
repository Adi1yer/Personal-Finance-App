export function formatPlaidSyncSummary(result: {
  ran: boolean;
  staged: number;
  posted: number;
  skipped: number;
  investment_staged: number;
  investment_posted: number;
  investment_skipped: number;
  holdings_updated: number;
}): string {
  if (!result.ran) {
    return "Up to date — next sync runs on schedule.";
  }
  const parts = [
    `${result.posted} bank posted`,
    `${result.staged} bank staged`,
    `${result.investment_posted} investment posted`,
    `${result.holdings_updated} holdings updated`,
  ].filter((p) => !p.startsWith("0 "));
  return parts.length ? `Synced: ${parts.join(", ")}` : "Sync complete.";
}
