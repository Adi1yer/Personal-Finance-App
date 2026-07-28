import type { PlaidAccount } from "../api/client";
import { formatMoney } from "../api/client";

export function plaidAccountTitle(pa: PlaidAccount): string {
  if (pa.official_name && pa.official_name !== pa.name) {
    return pa.official_name;
  }
  return pa.name;
}

export function plaidAccountDetails(pa: PlaidAccount): string {
  const parts: string[] = [];
  if (pa.mask) parts.push(`•••• ${pa.mask}`);
  if (pa.balance_current != null && pa.balance_current !== "") {
    const n = Number(pa.balance_current);
    if (!Number.isNaN(n)) {
      parts.push(
        pa.plaid_type === "credit" ? `balance owed ${formatMoney(Math.abs(n))}` : formatMoney(n)
      );
    }
  }
  if (pa.name === "CREDIT CARD" && !pa.mask && parts.length === 0) {
    parts.push("sync again to show last 4 digits");
  }
  return parts.join(" · ");
}
