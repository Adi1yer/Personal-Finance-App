import { FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, Input } from "../components/ui";

export default function LoginPage() {
  const { login, token, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  if (!loading && token) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setPending(true);
    try {
      await login(email, password);
    } catch (err) {
      setError((err as Error).message || "Sign in failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-surface-base px-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold text-white">Personal Finance</h1>
        <p className="mt-1 text-sm text-muted">Sign in to your profile</p>
        <form className="mt-8 space-y-4" onSubmit={onSubmit}>
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
            <label className="mb-1 block text-xs text-muted">Password</label>
            <Input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="text-right">
            <Link to="/login/forgot-password" className="text-xs text-accent hover:underline">
              Forgot password?
            </Link>
          </div>
          {error && <p className="text-xs text-negative">{error}</p>}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted">
          New here?{" "}
          <Link to="/login/register" className="text-accent hover:underline">
            Create a profile
          </Link>
        </p>
      </Card>
    </div>
  );
}
