import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { RecoveryCodeBox } from "../components/RecoveryCodeBox";
import { Button, Card, Input } from "../components/ui";

export default function SignUpPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setPending(true);
    try {
      const res = await register(email, password, displayName || undefined);
      setRecoveryCode(res.recovery_code);
    } catch (err) {
      setError((err as Error).message || "Could not create profile");
    } finally {
      setPending(false);
    }
  }

  if (recoveryCode) {
    return (
      <div className="flex min-h-full items-center justify-center bg-surface-base px-4">
        <Card className="w-full max-w-md p-8">
          <h1 className="text-2xl font-semibold text-white">Save your recovery code</h1>
          <p className="mt-2 text-sm text-muted">
            You need this to reset your password. We cannot email it — everything stays on
            this Mac.
          </p>
          <RecoveryCodeBox code={recoveryCode} className="mt-6" />
          <Button className="mt-6 w-full" onClick={() => navigate("/", { replace: true })}>
            I saved it — open my ledger
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-surface-base px-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold text-white">Create profile</h1>
        <p className="mt-1 text-sm text-muted">
          Your ledger stays on this Mac, tied to this login.
        </p>
        <form className="mt-8 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="mb-1 block text-xs text-muted">Display name (optional)</label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Email</label>
            <Input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Password (8+ characters)</label>
            <Input
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <p className="text-xs text-negative">{error}</p>}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Creating…" : "Create profile"}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted">
          Already have a profile?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </Card>
    </div>
  );
}
