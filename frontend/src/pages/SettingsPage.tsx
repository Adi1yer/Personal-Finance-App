import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api, type PlaidAccount } from "../api/client";
import { formatPlaidSyncSummary } from "../lib/plaidSync";
import { plaidLinkErrorHint, plaidRedirectUri } from "../lib/plaidLink";
import { plaidAccountDetails, plaidAccountTitle } from "../lib/plaidAccount";
import { Card, CardHeader, Button, Badge, Select, Input } from "../components/ui";
import { Cloud, CloudUpload, Link2, LogOut, RefreshCw, Server, User } from "lucide-react";

export default function SettingsPage() {
  const { profile, logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [linkError, setLinkError] = useState("");
  const [browserLinkMsg, setBrowserLinkMsg] = useState("");
  const [mapDraft, setMapDraft] = useState<Record<number, string>>({});
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMsg, setPasswordMsg] = useState("");
  const [newRecoveryCode, setNewRecoveryCode] = useState<string | null>(null);
  const [driveMsg, setDriveMsg] = useState("");

  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const plaidStatus = useQuery({ queryKey: ["plaidStatus"], queryFn: api.plaidStatus });
  const driveStatus = useQuery({
    queryKey: ["googleDriveStatus"],
    queryFn: api.googleDriveStatus,
  });
  const driveBackups = useQuery({
    queryKey: ["googleDriveBackups"],
    queryFn: api.googleDriveBackups,
    enabled: !!driveStatus.data?.connected,
  });
  const plaidAccounts = useQuery({
    queryKey: ["plaidAccounts"],
    queryFn: api.plaidAccounts,
    enabled: plaidStatus.data?.configured ?? false,
  });
  const ledgerAccounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.accounts(false),
  });

  const sync = useMutation({
    mutationFn: api.plaidSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["plaidStatus"] });
    },
  });

  const resetPlaid = useMutation({
    mutationFn: api.plaidReset,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["plaidStatus"] });
      qc.invalidateQueries({ queryKey: ["plaidAccounts"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
      setLinkError("");
    },
    onError: (e) => setLinkError((e as Error).message),
  });

  const changePassword = useMutation({
    mutationFn: () => api.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setPasswordMsg("Password updated.");
      setCurrentPassword("");
      setNewPassword("");
    },
    onError: (e) => setPasswordMsg((e as Error).message),
  });

  const regenRecovery = useMutation({
    mutationFn: api.regenerateRecovery,
    onSuccess: (data) => setNewRecoveryCode(data.recovery_code),
    onError: (e) => setPasswordMsg((e as Error).message),
  });

  const mapAccount = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: Parameters<typeof api.plaidMap>[1];
    }) => api.plaidMap(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plaidAccounts"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const connectBank = useCallback(async () => {
    setLinkError("");
    setBrowserLinkMsg("");
    try {
      const { url, browser } = await api.plaidBeginBrowserLink(plaidRedirectUri());
      setBrowserLinkMsg(
        [
          `Opened ${browser === "Safari" ? "Safari" : "your browser"} to connect your bank.`,
          "Complete login there, then return here to map accounts.",
          "",
          "Security warning on localhost HTTPS?",
          "• Safari: click Show Details → visit this website",
          "• Brave/Chrome: click Advanced → Proceed to 127.0.0.1",
          "• Or on that warning page, type: thisisunsafe (no box — just type it)",
          "• Permanent fix: brew install mkcert && make trust-cert",
          "",
          `Manual link (paste in your browser): ${url}`,
        ].join("\n")
      );
      qc.invalidateQueries({ queryKey: ["plaidStatus"] });
      const poll = window.setInterval(() => {
        qc.invalidateQueries({ queryKey: ["plaidStatus"] });
        qc.invalidateQueries({ queryKey: ["plaidAccounts"] });
      }, 4000);
      window.setTimeout(() => window.clearInterval(poll), 10 * 60 * 1000);
    } catch (e) {
      setLinkError(plaidLinkErrorHint((e as Error).message));
    }
  }, [qc]);

  const connectDrive = useCallback(async () => {
    setDriveMsg("");
    try {
      const { auth_url, browser } = await api.googleDriveConnect();
      setDriveMsg(
        [
          `Opened ${browser === "Safari" ? "Safari" : "your browser"} for Google sign-in.`,
          "Finish there, then return here — status updates in a few seconds.",
          "",
          `If nothing opened, paste this in Safari:\n${auth_url}`,
        ].join("\n")
      );
      const poll = window.setInterval(() => {
        qc.invalidateQueries({ queryKey: ["googleDriveStatus"] });
        qc.invalidateQueries({ queryKey: ["googleDriveBackups"] });
      }, 3000);
      window.setTimeout(() => window.clearInterval(poll), 5 * 60 * 1000);
    } catch (e) {
      setDriveMsg((e as Error).message);
    }
  }, [qc]);

  const backupNow = useMutation({
    mutationFn: api.googleDriveBackupNow,
    onSuccess: (data) => {
      setDriveMsg(`Uploaded ${data.name} (kept last ${data.kept}; pruned ${data.pruned}).`);
      qc.invalidateQueries({ queryKey: ["googleDriveStatus"] });
      qc.invalidateQueries({ queryKey: ["googleDriveBackups"] });
    },
    onError: (e) => setDriveMsg((e as Error).message),
  });

  const disconnectDrive = useMutation({
    mutationFn: api.googleDriveDisconnect,
    onSuccess: () => {
      setDriveMsg("Disconnected.");
      qc.invalidateQueries({ queryKey: ["googleDriveStatus"] });
      qc.invalidateQueries({ queryKey: ["googleDriveBackups"] });
    },
    onError: (e) => setDriveMsg((e as Error).message),
  });

  const restoreBackup = useMutation({
    mutationFn: (file_id: string) => api.googleDriveRestore(file_id),
    onSuccess: (data) => {
      setDriveMsg(data.message);
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
    },
    onError: (e) => setDriveMsg((e as Error).message),
  });

  const driveBusy =
    backupNow.isPending || disconnectDrive.isPending || restoreBackup.isPending;

  const ready = plaidStatus.data?.enabled && plaidStatus.data?.configured;

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-white">Settings</h1>
        <p className="mt-1 text-sm text-muted">Bank connections (like Moneydance+)</p>
      </header>

      <Card>
        <CardHeader title="Profile" subtitle="Your data is stored locally for this login" />
        <div className="flex items-center gap-3 p-5">
          <User className="h-5 w-5 text-accent" />
          <div className="flex-1 text-sm">
            <p className="text-white">{profile?.display_name}</p>
            <p className="text-muted">{profile?.email}</p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="gap-2"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title="Password" subtitle="Change password or create a new recovery code" />
        <div className="space-y-4 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-muted">Current password</label>
              <Input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted">New password</label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
          </div>
          <Button
            size="sm"
            disabled={!currentPassword || newPassword.length < 8 || changePassword.isPending}
            onClick={() => changePassword.mutate()}
          >
            Update password
          </Button>
          <div className="border-t border-surface-border pt-4">
            <p className="text-xs text-muted">
              {profile?.has_recovery_code
                ? "Generate a new recovery code if you lost the old one."
                : "No recovery code on file — generate one for forgot-password reset."}
            </p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-2"
              disabled={regenRecovery.isPending}
              onClick={() => regenRecovery.mutate()}
            >
              New recovery code
            </Button>
          </div>
          {newRecoveryCode && (
            <div className="rounded-lg border border-accent/40 bg-accent/10 p-3">
              <p className="text-xs text-muted">Save this code somewhere safe:</p>
              <p className="mt-1 font-mono text-white">{newRecoveryCode}</p>
            </div>
          )}
          {passwordMsg && <p className="text-xs text-muted">{passwordMsg}</p>}
        </div>
      </Card>

      <Card>
        <CardHeader title="System" />
        <div className="flex items-center gap-3 p-5">
          <Server className="h-5 w-5 text-accent" />
          <span className="flex-1 text-sm text-muted">Local API</span>
          <Badge tone={health.data?.status === "ok" ? "green" : "amber"}>
            {health.data?.status === "ok" ? "Online" : "Offline"}
          </Badge>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Google Drive backups"
          subtitle="Save the latest 5 ledger snapshots to your Drive (also on quit)"
        />
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap gap-2 text-xs text-muted">
            <span>
              {driveStatus.isLoading
                ? "Loading…"
                : !driveStatus.data?.configured
                  ? "Not configured in .env"
                  : driveStatus.data.connected
                    ? `Connected as ${driveStatus.data.email || "Google account"}`
                    : "Not connected"}
            </span>
            {driveStatus.data?.last_backup_at && (
              <span>· last backup {new Date(driveStatus.data.last_backup_at).toLocaleString()}</span>
            )}
          </div>
          {driveMsg && <p className="text-xs text-muted whitespace-pre-wrap">{driveMsg}</p>}
          <div className="flex flex-wrap gap-2">
            {!driveStatus.data?.connected ? (
              <Button
                className="gap-2"
                disabled={!driveStatus.data?.configured || driveBusy}
                onClick={() => void connectDrive()}
              >
                <Cloud className="h-4 w-4" />
                Connect Google Drive
              </Button>
            ) : (
              <>
                <Button
                  className="gap-2"
                  disabled={driveBusy}
                  onClick={() => backupNow.mutate()}
                >
                  <CloudUpload className="h-4 w-4" />
                  Backup now
                </Button>
                <Button
                  variant="secondary"
                  disabled={driveBusy}
                  onClick={() => qc.invalidateQueries({ queryKey: ["googleDriveBackups"] })}
                >
                  Refresh list
                </Button>
                <Button
                  variant="ghost"
                  className="text-negative"
                  disabled={driveBusy}
                  onClick={() => {
                    if (confirm("Disconnect Google Drive from this profile?")) {
                      disconnectDrive.mutate();
                    }
                  }}
                >
                  Disconnect
                </Button>
              </>
            )}
          </div>
          {driveStatus.data?.connected && (driveBackups.data?.backups?.length ?? 0) > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-300">Cloud snapshots</p>
              {driveBackups.data!.backups.map((b) => (
                <div
                  key={b.id}
                  className="flex items-center gap-2 rounded-lg border border-surface-border px-3 py-2 text-xs"
                >
                  <span className="min-w-0 flex-1 truncate text-slate-200">
                    {b.name || b.id}
                    {b.created_at ? (
                      <span className="text-muted"> · {new Date(b.created_at).toLocaleString()}</span>
                    ) : null}
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={driveBusy}
                    onClick={() => {
                      if (
                        confirm(
                          "Replace your local ledger with this Drive backup? A safety copy is kept next to the DB file."
                        )
                      ) {
                        restoreBackup.mutate(b.id);
                      }
                    }}
                  >
                    Restore
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Connect bank (Plaid)"
          subtitle="Opens Plaid in your browser (needed for OAuth banks)"
        />
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap gap-2 text-xs text-muted">
            <span>
              Status:{" "}
              {plaidStatus.isLoading
                ? "loading…"
                : plaidStatus.isError
                  ? "error"
                  : plaidStatus.data?.enabled
                    ? "enabled"
                    : "disabled"}{" "}
              · env {plaidStatus.data?.env ?? "—"}
            </span>
            {plaidStatus.data?.item_count ? (
              <span>· {plaidStatus.data.item_count} bank connection(s)</span>
            ) : null}
            {plaidStatus.data?.configured && (
              <span>
                · transactions every {plaidStatus.data.transactions_sync_days}d · holdings every{" "}
                {plaidStatus.data.holdings_sync_days}d
                {plaidStatus.data.cloud_scheduler_enabled ? " · cloud scheduler on" : ""}
              </span>
            )}
          </div>

          {plaidStatus.isError && (
            <div className="rounded-lg border border-negative/30 bg-negative/10 p-4 text-xs text-red-200/90">
              <p className="font-medium text-red-100">Could not load Plaid status</p>
              <p className="mt-2">{(plaidStatus.error as Error).message}</p>
              <p className="mt-2 text-muted">
                Try quitting the app (Cmd+Q) and reopening. If this persists, check{" "}
                <code className="text-white">~/Library/Application Support/PersonalFinance/logs/</code>
                .
              </p>
            </div>
          )}

          {!plaidStatus.isLoading && !plaidStatus.isError && !plaidStatus.data?.configured && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-200/90">
              <p className="font-medium text-amber-100">Plaid not configured</p>
              <p className="mt-2 leading-relaxed">
                Add to <code className="text-white">.env</code> in your project folder:
                PLAID_CLIENT_ID, PLAID_SECRET, ENCRYPTION_KEY, PLAID_ENABLED=true,
                PLAID_ENV=sandbox. Then restart the app (Cmd+Q).
              </p>
              <p className="mt-2">
                See <code className="text-white">docs/ACCOUNTS_AND_PLAID.md</code> in the
                project.
              </p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button className="gap-2" disabled={!ready} onClick={connectBank}>
              <Link2 className="h-4 w-4" />
              Connect bank
            </Button>
            <Button
              variant="secondary"
              className="gap-2"
              disabled={!ready || sync.isPending || resetPlaid.isPending}
              onClick={() => sync.mutate()}
            >
              <RefreshCw className={`h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} />
              Sync now (all accounts)
            </Button>
            {plaidStatus.data?.item_count ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-negative"
                disabled={resetPlaid.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      "Remove all bank connections and imported Plaid transactions? Your account names and manual balances (401k, HSA) are kept."
                    )
                  ) {
                    resetPlaid.mutate();
                  }
                }}
              >
                Remove bank connections
              </Button>
            ) : null}
          </div>

          {browserLinkMsg && (
            <p className="whitespace-pre-wrap text-xs text-accent">{browserLinkMsg}</p>
          )}
          {linkError && (
            <p className="whitespace-pre-wrap text-xs text-negative">{linkError}</p>
          )}
          {sync.data && (
            <p className="text-xs text-muted">{formatPlaidSyncSummary(sync.data)}</p>
          )}
          {plaidStatus.data?.last_transactions_sync_at && (
            <p className="text-xs text-muted">
              Last transaction sync:{" "}
              {new Date(plaidStatus.data.last_transactions_sync_at).toLocaleString()}
            </p>
          )}
          {plaidStatus.data?.last_holdings_sync_at && (
            <p className="text-xs text-muted">
              Last holdings sync:{" "}
              {new Date(plaidStatus.data.last_holdings_sync_at).toLocaleString()}
            </p>
          )}
        </div>
      </Card>

      {plaidAccounts.data && plaidAccounts.data.length > 0 && (
        <Card>
          <CardHeader
            title="Map Plaid accounts"
            subtitle="Match using last 4 digits and balance — sync first if missing"
          />
          <div className="divide-y divide-surface-border">
            {plaidAccounts.data.map((pa: PlaidAccount) => (
              <div key={pa.id} className="space-y-3 p-5">
                <div>
                  <p className="font-medium text-white">{plaidAccountTitle(pa)}</p>
                  {plaidAccountDetails(pa) && (
                    <p className="text-sm text-accent">{plaidAccountDetails(pa)}</p>
                  )}
                  <p className="text-xs text-muted">
                    {pa.institution_name}
                    {pa.plaid_type ? ` · ${pa.plaid_type}` : ""}
                    {pa.plaid_subtype ? ` / ${pa.plaid_subtype}` : ""}
                    {pa.ledger_account_name
                      ? ` → mapped to ${pa.ledger_account_name}`
                      : " → not mapped"}
                  </p>
                </div>
                {!pa.ledger_account_id && (
                  <div className="flex flex-wrap items-end gap-2">
                    <div>
                      <label className="mb-1 block text-xs text-muted">
                        Link to existing
                      </label>
                      <Select
                        value={mapDraft[pa.id] ?? ""}
                        onChange={(e) =>
                          setMapDraft((d) => ({ ...d, [pa.id]: e.target.value }))
                        }
                      >
                        <option value="">Select…</option>
                        {ledgerAccounts.data?.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <Button
                      size="sm"
                      disabled={!mapDraft[pa.id]}
                      onClick={() =>
                        mapAccount.mutate({
                          id: pa.id,
                          body: { ledger_account_id: Number(mapDraft[pa.id]) },
                        })
                      }
                    >
                      Link
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        mapAccount.mutate({
                          id: pa.id,
                          body: {
                            create_ledger_account: true,
                            ledger_account_name: pa.name,
                          },
                        })
                      }
                    >
                      Create new account
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <SetupConnectionsSection />
      <SetupHelpSection />
      <AppSettingsSection />
    </div>
  );
}

function SetupHelpSection() {
  const guides = useQuery({ queryKey: ["helpGuides"], queryFn: api.helpGuides });
  const [openSlug, setOpenSlug] = useState<string | null>(null);
  const guide = useQuery({
    queryKey: ["helpGuide", openSlug],
    queryFn: () => api.helpGuide(openSlug!),
    enabled: !!openSlug,
  });

  const checklist = (guides.data?.guides ?? []).filter((g) => g.slug !== "README");

  return (
    <Card>
      <CardHeader
        title="Setup help"
        subtitle="What to expect at each step — same path as a full-featured install"
      />
      <div className="space-y-3 p-5 text-sm">
        <p className="text-xs text-muted">
          Follow these in order the first time. The Advisor can also read these guides when you ask
          setup questions (requires Ollama).
        </p>
        <ol className="space-y-2">
          {checklist.map((g) => (
            <li key={g.slug}>
              <button
                type="button"
                className="w-full rounded-lg border border-surface-border bg-surface-raised/50 px-3 py-2 text-left hover:border-accent/40"
                onClick={() => setOpenSlug((s) => (s === g.slug ? null : g.slug))}
              >
                <div className="font-medium text-slate-100">{g.title}</div>
                {g.blurb ? <div className="mt-0.5 text-xs text-muted">{g.blurb}</div> : null}
              </button>
              {openSlug === g.slug && (
                <div className="mt-2 max-h-80 overflow-y-auto rounded-lg border border-surface-border bg-black/20 px-3 py-2 text-xs leading-relaxed text-slate-300 whitespace-pre-wrap">
                  {guide.isLoading
                    ? "Loading…"
                    : guide.isError
                      ? (guide.error as Error).message
                      : guide.data?.content}
                </div>
              )}
            </li>
          ))}
        </ol>
        {!guides.data && !guides.isLoading && (
          <p className="text-xs text-muted">Help guides unavailable — see docs/help/ in the repo.</p>
        )}
      </div>
    </Card>
  );
}

function SetupConnectionsSection() {
  const qc = useQueryClient();
  const setup = useQuery({ queryKey: ["setupStatus"], queryFn: api.setupStatus });
  const [plaidId, setPlaidId] = useState("");
  const [plaidSecret, setPlaidSecret] = useState("");
  const [plaidEnv, setPlaidEnv] = useState("sandbox");
  const [googleId, setGoogleId] = useState("");
  const [googleSecret, setGoogleSecret] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (setup.data?.plaid.env) setPlaidEnv(setup.data.plaid.env);
  }, [setup.data?.plaid.env]);

  const ensureKey = useMutation({
    mutationFn: api.ensureEncryptionKey,
    onSuccess: () => {
      setMsg("Encryption key ready.");
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const save = useMutation({
    mutationFn: () =>
      api.saveSetup({
        generate_encryption_key: !setup.data?.encryption_key_set,
        ...(plaidId.trim() ? { plaid_client_id: plaidId.trim() } : {}),
        ...(plaidSecret.trim() ? { plaid_secret: plaidSecret.trim() } : {}),
        plaid_env: plaidEnv,
        plaid_enabled: true,
        ...(googleId.trim() ? { google_oauth_client_id: googleId.trim() } : {}),
        ...(googleSecret.trim() ? { google_oauth_client_secret: googleSecret.trim() } : {}),
      }),
    onSuccess: () => {
      setMsg("Saved. Keys stay on this Mac in data/app_config.json (not committed to git).");
      setPlaidSecret("");
      setGoogleSecret("");
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
      qc.invalidateQueries({ queryKey: ["plaidStatus"] });
      qc.invalidateQueries({ queryKey: ["googleDriveStatus"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const s = setup.data;

  return (
    <Card>
      <CardHeader
        title="Connections setup"
        subtitle="Bring your own Plaid and Google keys — stored only on this Mac"
      />
      <div className="space-y-4 p-5 text-sm">
        <div className="flex flex-wrap gap-2 text-xs text-muted">
          <span>
            Encryption:{" "}
            {s?.encryption_key_set ? (
              <span className="text-positive">ready</span>
            ) : (
              <span className="text-amber-400">needed</span>
            )}
          </span>
          <span>
            · Plaid:{" "}
            {s?.plaid.configured ? (
              <span className="text-positive">configured ({s.plaid.env})</span>
            ) : (
              <span className="text-amber-400">not configured</span>
            )}
          </span>
          <span>
            · Google Drive:{" "}
            {s?.google_drive.configured ? (
              <span className="text-positive">configured</span>
            ) : (
              <span className="text-amber-400">not configured</span>
            )}
          </span>
        </div>

        {!s?.encryption_key_set && (
          <Button
            variant="secondary"
            size="sm"
            disabled={ensureKey.isPending}
            onClick={() => ensureKey.mutate()}
          >
            Generate encryption key
          </Button>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-muted">Plaid client ID</label>
            <Input
              placeholder={s?.plaid.client_id_masked || "from dashboard.plaid.com"}
              value={plaidId}
              onChange={(e) => setPlaidId(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Plaid secret</label>
            <Input
              type="password"
              placeholder={s?.plaid.secret_set ? "•••• saved" : "secret"}
              value={plaidSecret}
              onChange={(e) => setPlaidSecret(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Plaid environment</label>
            <Select value={plaidEnv} onChange={(e) => setPlaidEnv(e.target.value)}>
              <option value="sandbox">sandbox</option>
              <option value="production">production</option>
            </Select>
          </div>
          <div className="text-xs text-muted self-end pb-2">
            Redirect URI to allow in Plaid:{" "}
            <code className="text-slate-300">{s?.plaid.redirect_uri}</code>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Google OAuth client ID</label>
            <Input
              placeholder={s?.google_drive.client_id_masked || "Web application client"}
              value={googleId}
              onChange={(e) => setGoogleId(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Google OAuth client secret</label>
            <Input
              type="password"
              placeholder={s?.google_drive.secret_set ? "•••• saved" : "secret"}
              value={googleSecret}
              onChange={(e) => setGoogleSecret(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2 text-xs text-muted">
            Google redirect URI:{" "}
            <code className="text-slate-300">{s?.google_drive.redirect_uri}</code>
            {" · "}
            See docs/help/ (or Setup help below) for the full walkthrough.
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save connections"}
          </Button>
        </div>
        {msg && <p className="text-xs text-muted whitespace-pre-wrap">{msg}</p>}
      </div>
    </Card>
  );
}

function AppSettingsSection() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["appSettings"], queryFn: api.appSettings });
  const [smtp, setSmtp] = useState({ host: "", port: "587", user: "", password: "", from: "" });
  const [ollama, setOllama] = useState({ url: "http://localhost:11434", model: "llama3.1:latest" });
  const [goals, setGoals] = useState({ investing: "20", safety: "10", income: "" });
  const [loaded, setLoaded] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  useEffect(() => {
    if (!settings.data || loaded) return;
    const s = settings.data.settings;
    setSmtp({
      host: String(s.smtp_host ?? ""),
      port: String(s.smtp_port ?? 587),
      user: String(s.smtp_user ?? ""),
      password: String(s.smtp_password ?? ""),
      from: String(s.smtp_from ?? ""),
    });
    setOllama({
      url: String(s.ollama_url ?? "http://localhost:11434"),
      model: String(s.ollama_model ?? "llama3.1:latest"),
    });
    setGoals({
      investing: String(s.investing_pct_of_income ?? 20),
      safety: String(s.safety_net_pct_of_income ?? 10),
      income: s.annual_income_override != null ? String(s.annual_income_override) : "",
    });
    setLoaded(true);
  }, [settings.data, loaded]);

  const save = useMutation({
    mutationFn: () =>
      api.patchSettings({
        smtp_host: smtp.host,
        smtp_port: Number(smtp.port),
        smtp_user: smtp.user,
        smtp_password: smtp.password,
        smtp_from: smtp.from,
        ollama_url: ollama.url,
        ollama_model: ollama.model,
        investing_pct_of_income: Number(goals.investing),
        safety_net_pct_of_income: Number(goals.safety),
        annual_income_override: goals.income ? Number(goals.income) : null,
      }),
    onSuccess: () => {
      setStatusMsg("Preferences saved.");
      setLoaded(false);
      qc.invalidateQueries({ queryKey: ["appSettings"] });
    },
    onError: (e) => setStatusMsg((e as Error).message),
  });

  const testEmail = useMutation({
    mutationFn: () => api.testEmail(),
    onSuccess: (r) => setStatusMsg(`Test email ${r.status}`),
    onError: (e) => setStatusMsg((e as Error).message),
  });

  const checkSmtp = useMutation({
    mutationFn: () => api.checkSmtp(),
    onSuccess: (r) =>
      setStatusMsg(r.ok ? `SMTP OK (${r.host}:${r.port})` : `SMTP failed: ${r.error}`),
    onError: (e) => setStatusMsg((e as Error).message),
  });

  const importHedge = useMutation({
    mutationFn: () => api.importHedgeFundSettings(false),
    onSuccess: (r) => {
      setStatusMsg(
        r.imported.length
          ? `Imported from hedge fund: ${r.imported.join(", ")}`
          : r.reason === "hedge_env_missing"
            ? "Hedge-fund .env not found"
            : "Nothing new to import (already configured)"
      );
      setLoaded(false);
      qc.invalidateQueries({ queryKey: ["appSettings"] });
    },
    onError: (e) => setStatusMsg((e as Error).message),
  });

  return (
    <>
      <Card>
        <CardHeader
          title="Ollama advisor"
          subtitle="Uses the same local Ollama as ai-hedge-fund-production (llama3.1)"
        />
        <div className="space-y-2 p-4">
          <Input placeholder="URL" value={ollama.url} onChange={(e) => setOllama({ ...ollama, url: e.target.value })} />
          <Input placeholder="Model" value={ollama.model} onChange={(e) => setOllama({ ...ollama, model: e.target.value })} />
          {settings.data?.ollama && (
            <p className="text-xs text-muted">
              {settings.data.ollama.connected ? "Connected" : "Not connected"}
              {settings.data.ollama.model_loaded ? " · model loaded" : " · model not loaded"}
              {settings.data.ollama.models?.length
                ? ` · available: ${settings.data.ollama.models.join(", ")}`
                : ""}
            </p>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader
          title="SMTP & weekly digest"
          subtitle="Gmail app password via STARTTLS — same setup as your hedge-fund emails"
        />
        <div className="grid gap-2 p-4 sm:grid-cols-2">
          <Input placeholder="SMTP host (smtp.gmail.com)" value={smtp.host} onChange={(e) => setSmtp({ ...smtp, host: e.target.value })} />
          <Input placeholder="Port" value={smtp.port} onChange={(e) => setSmtp({ ...smtp, port: e.target.value })} />
          <Input placeholder="User / sender email" value={smtp.user} onChange={(e) => setSmtp({ ...smtp, user: e.target.value })} />
          <Input type="password" placeholder="App password" value={smtp.password} onChange={(e) => setSmtp({ ...smtp, password: e.target.value })} />
          <Input placeholder="From address" value={smtp.from} onChange={(e) => setSmtp({ ...smtp, from: e.target.value })} className="sm:col-span-2" />
        </div>
        <div className="flex flex-wrap gap-2 px-4 pb-4">
          {settings.data?.smtp?.hedge_env_available && (
            <Button size="sm" variant="secondary" onClick={() => importHedge.mutate()} disabled={importHedge.isPending}>
              Import from hedge fund
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={() => checkSmtp.mutate()} disabled={checkSmtp.isPending}>
            Check SMTP
          </Button>
          <Button size="sm" variant="secondary" onClick={() => testEmail.mutate()} disabled={testEmail.isPending}>
            Test email
          </Button>
        </div>
        {settings.data?.smtp && (
          <p className="px-4 pb-4 text-xs text-muted">
            {settings.data.smtp.configured ? "SMTP configured" : "SMTP not configured"}
            {settings.data.smtp.digest_email ? ` · digest → ${settings.data.smtp.digest_email}` : ""}
          </p>
        )}
      </Card>
      <Card>
        <CardHeader title="Annual goals" />
        <div className="grid gap-2 p-4 sm:grid-cols-3">
          <Input placeholder="Investing %" value={goals.investing} onChange={(e) => setGoals({ ...goals, investing: e.target.value })} />
          <Input placeholder="Safety net %" value={goals.safety} onChange={(e) => setGoals({ ...goals, safety: e.target.value })} />
          <Input placeholder="Income override" value={goals.income} onChange={(e) => setGoals({ ...goals, income: e.target.value })} />
        </div>
      </Card>
      <Button onClick={() => save.mutate()} disabled={save.isPending}>
        Save preferences
      </Button>
      {statusMsg && <p className="text-xs text-muted">{statusMsg}</p>}
    </>
  );
}
