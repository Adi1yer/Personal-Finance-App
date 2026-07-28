declare global {
  interface Window {
    Plaid?: {
      create: (config: {
        token: string;
        receivedRedirectUri?: string;
        onSuccess: (public_token: string, metadata: unknown) => void;
        onExit?: (err: unknown, metadata: unknown) => void;
      }) => { open: () => void };
    };
  }
}

export function loadPlaidScript(): Promise<void> {
  if (window.Plaid) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Failed to load Plaid Link"));
    document.head.appendChild(s);
  });
}

export function plaidRedirectUri(): string {
  return `${window.location.origin}/oauth/plaid.html`;
}

export function formatPlaidLinkError(err: unknown): string {
  if (!err) return "";
  if (typeof err === "string") {
    try {
      const parsed = JSON.parse(err) as Record<string, unknown>;
      if (parsed.error_message || parsed.display_message) {
        return formatPlaidLinkError(parsed);
      }
    } catch {
      return err;
    }
    return err;
  }
  if (err instanceof Error) return err.message;
  if (typeof err === "object") {
    const e = err as Record<string, unknown>;
    const msg = e.display_message ?? e.error_message ?? e.message;
    const code = e.error_code;
    if (typeof msg === "string" && msg) {
      return typeof code === "string" ? `${msg} (${code})` : msg;
    }
  }
  try {
    return JSON.stringify(err);
  } catch {
    return "Plaid Link failed";
  }
}

export function plaidLinkErrorHint(message: string): string {
  if (message.includes("INVALID_LINK_CUSTOMIZATION") || message.includes("Data Transparency")) {
    return (
      `${formatPlaidLinkError(message)}\n\n` +
      "Plaid requires Data Transparency setup for production:\n" +
      "1. Open https://dashboard.plaid.com/link/data-transparency-v5\n" +
      "2. Edit your Link customization → Data Transparency\n" +
      "3. Select at least one use case (e.g. “Track and manage your finances”)\n" +
      "4. Click Publish (required — saving alone is not enough)\n" +
      "5. Try Connect bank again"
    );
  }
  return chaseOAuthHint(message);
}

export function chaseOAuthHint(message: string): string {
  const lower = message.toLowerCase();
  if (
    lower.includes("chase") ||
    lower.includes("oauth") ||
    lower.includes("update your app") ||
    lower.includes("institution")
  ) {
    return (
      `${message}\n\n` +
      "Chase requires OAuth in production. In the Plaid Dashboard:\n" +
      "1. Team Settings → API → add allowed redirect URI: " +
      plaidRedirectUri() +
      "\n" +
      "2. OAuth Institutions → confirm Chase is enabled (can take a few weeks after production approval).\n" +
      "3. Quit and reopen the app so it uses HTTPS locally."
    );
  }
  return message;
}
