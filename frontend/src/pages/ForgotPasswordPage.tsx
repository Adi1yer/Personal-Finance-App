import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, Input } from "../components/ui";

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setPending(true);
    try {
      await api.resetPassword(email, recoveryCode, newPassword);
      await login(email, newPassword);
      navigate("/");
    } catch (err) {
      setError((err as Error).message || "Could not reset password");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-surface-base px-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold text-white">Reset password</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Enter the recovery code you saved when you created your profile (e.g.{" "}
          <span className="text-slate-300">amber-maple-stone-river</span>).
        </p>
        <form className="mt-8 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="mb-1 block text-xs text-muted">Email</label>
            <Input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Recovery code</label>
            <Input
              required
              placeholder="word-word-word-word"
              value={recoveryCode}
              onChange={(e) => setRecoveryCode(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">New password</label>
            <Input
              type="password"
              autoComplete="new-password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          {error && <p className="text-xs text-negative">{error}</p>}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Updating…" : "Set new password"}
          </Button>
        </form>
        <p className="mt-6 text-center text-xs text-muted">
          No recovery code? From the project folder in Terminal:{" "}
          <code className="text-slate-300">make reset-password EMAIL=you@example.com</code>
        </p>
        <p className="mt-4 text-center text-sm text-muted">
          <Link to="/login" className="text-accent hover:underline">
            Back to sign in
          </Link>
        </p>
      </Card>
    </div>
  );
}
