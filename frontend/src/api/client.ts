const API_BASE =
  window.personalFinance?.apiBase?.replace(/\/$/, "") ||
  (import.meta.env.DEV
    ? ""
    : typeof window !== "undefined"
      ? window.location.origin
      : "http://127.0.0.1:8000");

let authToken: string | null =
  typeof localStorage !== "undefined" ? localStorage.getItem("pf_auth_token") : null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

export interface ProfileSession {
  profile_id: string;
  email: string;
  display_name: string;
  has_recovery_code?: boolean;
}

export interface AuthResponse {
  access_token: string;
  profile_id: string;
  email: string;
  display_name: string;
}

export interface RegisterResponse extends AuthResponse {
  recovery_code: string;
}

function parseErrorMessage(text: string): string {
  try {
    const j = JSON.parse(text) as { detail?: string | { msg?: string }[] };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail) && j.detail[0]?.msg) return j.detail[0].msg;
  } catch {
    /* plain text */
  }
  return text || "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    setAuthToken(null);
    if (typeof localStorage !== "undefined") localStorage.removeItem("pf_auth_token");
    if (!path.includes("/auth/")) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface Account {
  id: number;
  name: string;
  slug: string;
  account_type: string;
  subtype: string;
  sync_source: string;
  institution_id: number | null;
  balance: string | null;
}

export interface AccountInput {
  name: string;
  account_type: string;
  subtype: string;
  sync_source?: string;
  institution_id?: number | null;
}

export interface Institution {
  id: number;
  name: string;
  slug: string;
}

export interface Transaction {
  id: number;
  txn_date: string;
  payee: string;
  is_transfer: boolean;
  entries: {
    id: number;
    account_id: number;
    amount: string;
    is_cleared: boolean;
  }[];
}

export interface PlaidStatus {
  enabled: boolean;
  configured: boolean;
  env: string;
  item_count: number;
  transactions_sync_days: number;
  holdings_sync_days: number;
  cloud_scheduler_enabled: boolean;
  last_transactions_sync_at: string | null;
  last_holdings_sync_at: string | null;
}

export interface PlaidAccount {
  id: number;
  plaid_account_id: string;
  name: string;
  official_name: string | null;
  mask: string | null;
  balance_current: string | null;
  plaid_type: string | null;
  plaid_subtype: string | null;
  institution_name: string | null;
  ledger_account_id: number | null;
  ledger_account_name: string | null;
}

export interface PlaidSyncResult {
  ran: boolean;
  staged: number;
  posted: number;
  skipped: number;
  investment_staged: number;
  investment_posted: number;
  investment_skipped: number;
  holdings_updated: number;
  health?: SyncHealth;
}

export interface SyncHealth {
  ok: boolean;
  suspected_duplicate_clusters: number;
  balance_mismatches: Array<{
    account_id: number;
    account_name: string;
    ledger_balance: string;
    plaid_balance: string;
    delta: string;
  }>;
  staging_pending: number;
  warnings: string[];
  sync: Record<string, number | boolean>;
}

export interface BalanceExplain {
  account_id: number;
  account_name: string;
  ledger_balance: string;
  plaid_balance: string | null;
  delta: string | null;
  opening_balance: string;
  uncleared_total: string;
  uncleared_count: number;
  recent_voids: Array<Record<string, string>>;
  cross_post_candidates: Array<Record<string, string>>;
  hints: string[];
}

export interface DuplicateCluster {
  id: number;
  account_id: number;
  account_name: string;
  payee_key: string;
  amount: string;
  confidence: string;
  reasons: string[];
  transactions: Array<{
    transaction_id: number;
    entry_id: number;
    txn_date: string;
    payee: string;
    amount: string;
    is_cleared: boolean;
    source: string;
  }>;
}

export interface CategoryRule {
  id: number;
  pattern: string;
  category_id: number;
  category_name?: string | null;
  match_field: string;
  priority: number;
  amount_direction: string;
  transactions_updated?: number;
}

export interface GoalsProgress {
  year: number;
  month: number;
  annual_income: string;
  income_source: string;
  investing: {
    pct_of_income: number;
    annual_target: string;
    ytd_actual: string;
    pace_target: string;
    shortfall_vs_pace?: string;
    ahead_of_pace?: string;
    remaining_to_annual?: string;
    on_track: boolean;
    by_account?: Array<{
      account_id: number;
      name: string;
      subtype: string;
      ytd_contributions: string;
    }>;
  };
  safety_net: {
    pct_of_income: number;
    target_balance: string;
    current_balance: string;
    shortfall_vs_target?: string;
    on_track: boolean;
  };
}

export interface ProjectionResult {
  horizon_years: number;
  assumptions: { stock_appreciation_pct: number; dividend_growth_pct: number };
  current: { portfolio_value: string; annual_dividend_income: string };
  projected_final: Record<string, string>;
  series: Array<Record<string, string | number>>;
  accounts: Array<Record<string, string | number>>;
}

export interface AppSettings {
  settings: Record<string, unknown>;
  ollama: {
    connected: boolean;
    models: string[];
    configured_model: string;
    model_loaded: boolean;
    error?: string;
  };
  smtp?: {
    configured: boolean;
    host: string;
    from: string;
    digest_email: string;
    hedge_env_available: boolean;
  };
}

export interface CategorySuggestion {
  category_id: number;
  category_name: string;
  rule_id: number | null;
  label: string | null;
}

export interface RegisterRow {
  entry_id: number;
  transaction_id: number;
  txn_date: string;
  payee: string;
  memo: string | null;
  charge: string | null;
  payment: string | null;
  running_balance: string;
  category_id: number | null;
  category_name: string | null;
  category_suggestions: CategorySuggestion[];
  remember_pattern: string | null;
  category_conflict: boolean;
  activity_label: string | null;
  cash_direction: "outflow" | "inflow" | null;
  is_cleared: boolean;
  is_transfer: boolean;
  source: string;
  investment_type: string | null;
  investment_subtype: string | null;
  security_name: string | null;
  quantity: string | null;
  price: string | null;
}

export interface HoldingSummary {
  ticker: string;
  security_name: string;
  quantity: string;
  cost_basis_total: string;
  market_value: string;
  gain: string;
}

export interface AccountRegisterResponse {
  account_id: number;
  account_name: string;
  account_subtype: string;
  amount_out_label: string;
  amount_in_label: string;
  balance_column_label: string;
  tracking_start_date: string | null;
  opening_balance: string;
  current_balance: string;
  cash_balance: string | null;
  portfolio_value: string | null;
  holdings: HoldingSummary[];
  holdings_as_of_date: string | null;
  cleared_balance: string;
  uncleared_balance: string;
  uncleared_count: number;
  plaid_balance_current: string | null;
  total_count: number;
  rows: RegisterRow[];
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  category_type: string;
}

export interface CashFlowReport {
  start: string;
  end: string;
  operating: { label: string; amount: string }[];
  investing: { label: string; amount: string }[];
  financing: { label: string; amount: string }[];
  net_operating: string;
  net_investing: string;
  net_financing: string;
  net_change: string;
}

export interface NetWorthHistoryPoint {
  date: string;
  net_worth: string;
  total_assets: string;
  total_liabilities: string;
}

export interface NetWorthHistoryReport {
  start: string;
  end: string;
  points: NetWorthHistoryPoint[];
}

export interface ReportsReadiness {
  ready: boolean;
  stale_accounts: {
    account_id: number;
    account_name: string;
    reason: string;
    last_updated?: string;
  }[];
}

export interface ReconcilePreview {
  account_id: number;
  statement_end_date: string;
  ending_balance: string;
  opening_balance: string;
  ledger_balance: string;
  cleared_balance: string;
  difference: string;
  uncleared_entries: {
    entry_id: number;
    txn_date: string;
    payee: string;
    charge: string | null;
    payment: string | null;
  }[];
}

export interface BalanceSheetReport {
  as_of: string;
  assets: { account_name: string; balance: string }[];
  liabilities: { account_name: string; balance: string }[];
  total_assets: string;
  total_liabilities: string;
  net_worth: string;
}

export interface IncomeStatementReport {
  start: string;
  end: string;
  income: { account_name: string; total: string }[];
  expenses: { account_name: string; total: string }[];
  total_income: string;
  total_expenses: string;
  net_income: string;
}

export interface QuarterlyMetrics {
  net_worth: string;
  net_worth_change: string | null;
  total_income: string;
  total_expenses: string;
  net_income: string;
  savings_rate: string | null;
  spending_by_category: { category: string; amount: string }[];
}

export interface MonthlyMetrics {
  year: number;
  month: number;
  start: string;
  end: string;
  total_income: string;
  total_expenses: string;
  net_income: string;
  prior_total_income: string;
  prior_total_expenses: string;
  prior_net_income: string;
  spending_by_category: { category: string; amount: string }[];
}

export interface OverviewAccountLine {
  id: number;
  name: string;
  balance: string;
  sync_source: string;
  subtype: string;
  last_updated_at: string | null;
  last_updated_label: string;
  register_pending_count: number;
  holdings_as_of?: string | null;
  quotes_refreshed_at?: string | null;
}

export interface OverviewGroup {
  key: string;
  label: string;
  total: string;
  accounts: OverviewAccountLine[];
}

export interface OverviewResponse {
  net_worth: string;
  total_assets: string;
  total_liabilities: string;
  groups: OverviewGroup[];
  cash_total: string;
  monthly_expenses: string;
  goals_progress?: GoalsProgress;
  advisor_insights?: string[];
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, displayName?: string) =>
    request<RegisterResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        display_name: displayName ?? "",
      }),
    }),
  resetPassword: (email: string, recoveryCode: string, newPassword: string) =>
    request<AuthResponse>("/api/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        email,
        recovery_code: recoveryCode,
        new_password: newPassword,
      }),
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  regenerateRecovery: () =>
    request<{ recovery_code: string }>("/api/v1/auth/regenerate-recovery", {
      method: "POST",
    }),
  session: () => request<ProfileSession>("/api/v1/auth/session"),
  accounts: (includeSystem = false) =>
    request<Account[]>(`/api/v1/accounts?include_system=${includeSystem}`),
  createAccount: (body: AccountInput) =>
    request<Account>("/api/v1/accounts", { method: "POST", body: JSON.stringify(body) }),
  updateAccount: (id: number, body: Partial<AccountInput>) =>
    request<Account>(`/api/v1/accounts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  archiveAccount: (id: number) =>
    request<void>(`/api/v1/accounts/${id}`, { method: "DELETE" }),
  institutions: () => request<Institution[]>("/api/v1/institutions"),
  createInstitution: (name: string) =>
    request<Institution>("/api/v1/institutions", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  categories: () => request<Category[]>("/api/v1/categories"),
  createCategory: (body: { name: string; category_type: "expense" | "income" }) =>
    request<Category>("/api/v1/categories", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateCategory: (id: number, body: { name?: string; category_type?: "expense" | "income" }) =>
    request<Category>(`/api/v1/categories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteCategory: (id: number) =>
    request<void>(`/api/v1/categories/${id}`, { method: "DELETE" }),
  accountRegister: (accountId: number) =>
    request<AccountRegisterResponse>(`/api/v1/register?account_id=${accountId}`),
  patchEntry: (entryId: number, body: { category_id?: number | null; is_cleared?: boolean }) =>
    request<unknown>(`/api/v1/entries/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  createCategoryRule: (body: {
    pattern: string;
    category_id: number;
    match_field?: string;
    priority?: number;
    amount_direction?: "any" | "outflow" | "inflow";
  }) =>
    request<CategoryRule>("/api/v1/category-rules", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createTransaction: (body: {
    txn_date: string;
    payee: string;
    memo?: string;
    entries: { account_id: number; amount: string; category_id?: number }[];
  }) =>
    request<Transaction>("/api/v1/transactions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createCardPurchase: (body: {
    txn_date: string;
    card_account_id: number;
    expense_account_id: number;
    category_id: number;
    amount: string;
    payee?: string;
    memo?: string;
  }) =>
    request<Transaction>("/api/v1/transactions/card-purchase", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createTransfer: (body: {
    txn_date: string;
    from_account_id: number;
    to_account_id: number;
    amount: string;
    payee?: string;
    memo?: string;
  }) =>
    request<Transaction>("/api/v1/transactions/transfer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reconcilePreview: (accountId: number, statementEndDate: string, endingBalance: string) =>
    request<ReconcilePreview>(
      `/api/v1/reconcile/${accountId}/preview?statement_end_date=${statementEndDate}&ending_balance=${endingBalance}`
    ),
  reconcileAccount: (
    accountId: number,
    body: { statement_end_date: string; ending_balance: string; cleared_entry_ids: number[] }
  ) =>
    request<unknown>(`/api/v1/reconcile/${accountId}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cashFlowStatement: (start: string, end: string) =>
    request<CashFlowReport>(`/api/v1/reports/cash-flow?start=${start}&end=${end}`),
  reportsReadiness: (asOf?: string) =>
    request<ReportsReadiness>(
      `/api/v1/reports/readiness${asOf ? `?as_of=${asOf}` : ""}`
    ),
  exportReportPackage: async (year: number, quarter: number, format: "csv" | "pdf") => {
    const headers: Record<string, string> = {};
    if (authToken) headers.Authorization = `Bearer ${authToken}`;
    const res = await fetch(
      `${API_BASE}/api/v1/reports/package?year=${year}&quarter=${quarter}&format=${format}`,
      { headers }
    );
    if (!res.ok) throw new Error(parseErrorMessage(await res.text()));
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match?.[1] || `financials_q${quarter}_${year}.${format === "csv" ? "csv" : "txt"}`;
    return { blob, filename };
  },
  transactions: (accountId?: number) =>
    request<Transaction[]>(
      accountId ? `/api/v1/transactions?account_id=${accountId}` : "/api/v1/transactions"
    ),
  balanceSheet: (asOf: string) =>
    request<BalanceSheetReport>(`/api/v1/reports/balance-sheet?as_of=${asOf}`),
  incomeStatement: (start: string, end: string) =>
    request<IncomeStatementReport>(
      `/api/v1/reports/income-statement?start=${start}&end=${end}`
    ),
  quarterlyMetrics: (year: number, quarter: number) =>
    request<QuarterlyMetrics>(
      `/api/v1/reports/metrics/quarterly?year=${year}&quarter=${quarter}`
    ),
  monthlyMetrics: (year: number, month: number) =>
    request<MonthlyMetrics>(
      `/api/v1/reports/metrics/monthly?year=${year}&month=${month}`
    ),
  netWorthHistory: () => request<NetWorthHistoryReport>("/api/v1/reports/net-worth/history"),
  overview: () => request<OverviewResponse>("/api/v1/overview"),
  health: () => request<{ status: string }>("/health"),
  plaidStatus: () => request<PlaidStatus>("/api/v1/plaid/status"),
  plaidAccounts: () => request<PlaidAccount[]>("/api/v1/plaid/accounts"),
  plaidBeginBrowserLink: (redirect_uri?: string) =>
    request<{ opened: boolean; url: string; browser?: string }>(
      "/api/v1/plaid/begin-browser-link",
      {
        method: "POST",
        body: JSON.stringify(redirect_uri ? { redirect_uri } : {}),
      }
    ),
  plaidLinkToken: (redirect_uri?: string) =>
    request<{ link_token: string; redirect_uri?: string }>("/api/v1/plaid/link-token", {
      method: "POST",
      body: JSON.stringify(redirect_uri ? { redirect_uri } : {}),
    }),
  plaidExchange: (public_token: string) =>
    request<{ item_id: string }>("/api/v1/plaid/exchange", {
      method: "POST",
      body: JSON.stringify({ public_token }),
    }),
  plaidMap: (
    plaidAccountId: number,
    body: {
      ledger_account_id?: number;
      create_ledger_account?: boolean;
      ledger_account_name?: string;
      account_type?: string;
      subtype?: string;
    }
  ) =>
    request<PlaidAccount>(`/api/v1/plaid/accounts/${plaidAccountId}/map`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  plaidSync: () =>
    request<PlaidSyncResult>("/api/v1/plaid/sync", {
      method: "POST",
    }),
  plaidScheduledSync: () =>
    request<PlaidSyncResult>("/api/v1/plaid/sync/scheduled", {
      method: "POST",
    }),
  plaidReset: () =>
    request<{
      transactions_deleted: number;
      entries_deleted: number;
      staging_deleted: number;
      accounts_unmapped: number;
      plaid_accounts_deleted: number;
      plaid_items_deleted: number;
    }>("/api/v1/plaid/reset", { method: "POST" }),
  createAccountMark: (body: {
    account_id: number;
    as_of_date: string;
    market_value: string;
    note?: string;
    total_contributions?: string;
  }) =>
    request<unknown>("/api/v1/accounts/marks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createAccountContribution: (body: {
    account_id: number;
    amount: string;
    txn_date: string;
    memo?: string;
  }) =>
    request<{ transaction_id: number; account_id: number; amount: string; txn_date: string }>(
      "/api/v1/accounts/contributions",
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ),
  syncHealth: () => request<SyncHealth>("/api/v1/plaid/sync/health"),
  balanceExplain: (accountId: number) =>
    request<BalanceExplain>(`/api/v1/register/${accountId}/balance-explain`),
  duplicates: () => request<DuplicateCluster[]>("/api/v1/review/duplicates"),
  mergeDuplicate: (clusterId: number, keepTransactionId: number) =>
    request<{ voided: number; kept: number }>(`/api/v1/review/duplicates/${clusterId}/merge`, {
      method: "POST",
      body: JSON.stringify({ keep_transaction_id: keepTransactionId }),
    }),
  keepBothDuplicates: (clusterId: number) =>
    request<{ status: string }>(`/api/v1/review/duplicates/${clusterId}/keep-both`, {
      method: "POST",
    }),
  categoryRules: () => request<CategoryRule[]>("/api/v1/category-rules"),
  updateCategoryRule: (id: number, body: Partial<CategoryRule>) =>
    request<CategoryRule>(`/api/v1/category-rules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteCategoryRule: (id: number) =>
    request<void>(`/api/v1/category-rules/${id}`, { method: "DELETE" }),
  reapplyCategoryRules: (days = 90) =>
    request<{ updated: number }>(`/api/v1/category-rules/reapply?days=${days}`, {
      method: "POST",
    }),
  goalsProgress: () => request<GoalsProgress>("/api/v1/goals/progress"),
  projections: (params?: { horizon_years?: number; stock_appreciation_pct?: number; dividend_growth_pct?: number }) => {
    const q = new URLSearchParams();
    if (params?.horizon_years != null) q.set("horizon_years", String(params.horizon_years));
    if (params?.stock_appreciation_pct != null) q.set("stock_appreciation_pct", String(params.stock_appreciation_pct));
    if (params?.dividend_growth_pct != null) q.set("dividend_growth_pct", String(params.dividend_growth_pct));
    return request<ProjectionResult>(`/api/v1/goals/projections?${q}`);
  },
  appSettings: () => request<AppSettings>("/api/v1/settings"),
  setupStatus: () =>
    request<{
      encryption_key_set: boolean;
      plaid: {
        configured: boolean;
        enabled: boolean;
        env: string;
        client_id_set: boolean;
        secret_set: boolean;
        client_id_masked: string | null;
        redirect_uri: string;
      };
      google_drive: {
        configured: boolean;
        client_id_set: boolean;
        secret_set: boolean;
        client_id_masked: string | null;
        redirect_uri: string;
      };
      config_file: string | null;
      has_local_overrides: boolean;
    }>("/api/v1/setup/status"),
  ensureEncryptionKey: () =>
    request<{ encryption_key_set: boolean }>("/api/v1/setup/ensure-encryption-key", {
      method: "POST",
    }),
  saveSetup: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/v1/setup", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchSettings: (settings: Record<string, unknown>) =>
    request<AppSettings>("/api/v1/settings", {
      method: "PATCH",
      body: JSON.stringify({ settings }),
    }),
  testEmail: (to_addr?: string) =>
    request<{ status: string }>("/api/v1/settings/test-email", {
      method: "POST",
      body: JSON.stringify(to_addr ? { to_addr } : {}),
    }),
  checkSmtp: () =>
    request<{ ok: boolean; error?: string; host?: string; port?: number }>(
      "/api/v1/settings/check-smtp",
      { method: "POST" }
    ),
  importHedgeFundSettings: (overwrite = false) =>
    request<{
      imported: string[];
      source: string | null;
      smtp_ready?: boolean;
      reason?: string;
    }>(`/api/v1/settings/import-hedge-fund?overwrite=${overwrite}`, { method: "POST" }),
  advisorChat: (message: string, conversation_id?: number | null, page_context?: Record<string, unknown>) =>
    request<{
      reply: string;
      conversation_id: number;
      message_id?: number;
      pending_actions?: Array<Record<string, unknown>>;
      title?: string;
      compacted?: boolean;
      forked?: boolean;
    }>("/api/v1/advisor/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id, page_context }),
    }),
  editAdvisorMessage: (
    conversationId: number,
    messageId: number,
    content: string,
    fork = false
  ) =>
    request<{
      reply: string;
      conversation_id: number;
      message_id?: number;
      pending_actions?: Array<Record<string, unknown>>;
      title?: string;
      compacted?: boolean;
      forked?: boolean;
    }>(`/api/v1/advisor/conversations/${conversationId}/messages/${messageId}/edit`, {
      method: "POST",
      body: JSON.stringify({ content, fork }),
    }),
  advisorHistory: () => request<Array<{ role: string; content: string }>>("/api/v1/advisor/history"),
  advisorConversations: () =>
    request<
      Array<{
        id: number;
        title: string;
        updated_at: string | null;
        created_at: string | null;
        message_count: number;
      }>
    >("/api/v1/advisor/conversations"),
  createAdvisorConversation: (title = "New chat") =>
    request<{
      id: number;
      title: string;
      updated_at: string | null;
      created_at: string | null;
      message_count: number;
    }>("/api/v1/advisor/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  renameAdvisorConversation: (id: number, title: string) =>
    request<{
      id: number;
      title: string;
      updated_at: string | null;
      created_at: string | null;
      message_count: number;
    }>(`/api/v1/advisor/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteAdvisorConversation: (id: number) =>
    request<void>(`/api/v1/advisor/conversations/${id}`, { method: "DELETE" }),
  advisorConversationMessages: (id: number) =>
    request<Array<{ id: number; role: string; content: string; created_at: string | null }>>(
      `/api/v1/advisor/conversations/${id}/messages`
    ),
  advisorInsights: () => request<{ insights: string[] }>("/api/v1/advisor/insights"),
  approveAdvisorAction: (actionId: number, approved: boolean) =>
    request<Record<string, unknown>>(`/api/v1/advisor/actions/${actionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    }),
  recurringTransactions: () =>
    request<Array<Record<string, string | number>>>("/api/v1/alerts/recurring"),
  fundHoldings: (accountId: number) =>
    request<Array<{ id: number; ticker: string; allocation_pct: string | null; quantity: string | null }>>(
      `/api/v1/accounts/${accountId}/fund-holdings`
    ),
  createFundHolding: (accountId: number, body: { ticker: string; allocation_pct?: string; quantity?: string }) =>
    request<{ id: number; ticker: string }>(`/api/v1/accounts/${accountId}/fund-holdings`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteFundHolding: (holdingId: number) =>
    request<void>(`/api/v1/accounts/fund-holdings/${holdingId}`, { method: "DELETE" }),
  resolveCardPayment: (payee: string) =>
    request<Record<string, unknown>>(`/api/v1/entries/card-payment/resolve?payee=${encodeURIComponent(payee)}`),
  mapCardPayment: (mask: string, account_id: number) =>
    request<Record<string, unknown>>("/api/v1/entries/card-payment/map", {
      method: "POST",
      body: JSON.stringify({ mask, account_id }),
    }),
  googleDriveStatus: () =>
    request<{
      configured: boolean;
      connected: boolean;
      email: string | null;
      folder_id: string | null;
      last_backup_at: string | null;
      redirect_uri?: string;
    }>("/api/v1/google-drive/status"),
  googleDriveConnect: () =>
    request<{ auth_url: string; state: string; browser?: string }>(
      "/api/v1/google-drive/connect",
      {
        method: "POST",
      }
    ),
  googleDriveDisconnect: () =>
    request<{ status: string }>("/api/v1/google-drive/disconnect", { method: "POST" }),
  googleDriveBackups: () =>
    request<{
      backups: Array<{ id: string; name: string | null; created_at: string | null; size?: string }>;
    }>("/api/v1/google-drive/backups"),
  googleDriveBackupNow: () =>
    request<{
      file_id: string;
      name: string;
      created_at: string;
      pruned: number;
      kept: number;
    }>("/api/v1/google-drive/backup", { method: "POST" }),
  googleDriveRestore: (file_id: string) =>
    request<{
      restored_from: string;
      file_id: string;
      local_safety_copy: string | null;
      message: string;
    }>("/api/v1/google-drive/restore", {
      method: "POST",
      body: JSON.stringify({ file_id }),
    }),
};

export function formatMoney(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
}

export function signedMoney(value: string | number, opts?: { showPlus?: boolean }): string {
  const n = Number(value);
  const formatted = formatMoney(Math.abs(n));
  if (n < 0) return `−${formatted}`;
  if (n > 0 && opts?.showPlus) return `+${formatted}`;
  return formatted;
}
