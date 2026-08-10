import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, setAuthToken, type ProfileSession } from "../api/client";

const STORAGE_KEY = "pf_auth_token";

type AuthState = {
  token: string | null;
  profile: ProfileSession | null;
  loading: boolean;
};

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    displayName?: string
  ) => Promise<{ recovery_code: string }>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const [profile, setProfile] = useState<ProfileSession | null>(null);
  const [loading, setLoading] = useState(true);

  const persist = useCallback((next: string | null) => {
    setToken(next);
    setAuthToken(next);
    if (next) localStorage.setItem(STORAGE_KEY, next);
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const logout = useCallback(() => {
    persist(null);
    setProfile(null);
  }, [persist]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) {
        setProfile(null);
        setLoading(false);
        return;
      }
      setAuthToken(token);
      try {
        const session = await api.session();
        if (!cancelled) setProfile(session);
      } catch {
        if (!cancelled) logout();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.login(email, password);
      persist(res.access_token);
      setProfile({
        profile_id: res.profile_id,
        email: res.email,
        display_name: res.display_name,
      });
    },
    [persist]
  );

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const res = await api.register(email, password, displayName);
      persist(res.access_token);
      setProfile({
        profile_id: res.profile_id,
        email: res.email,
        display_name: res.display_name,
        has_recovery_code: true,
      });
      return { recovery_code: res.recovery_code };
    },
    [persist]
  );

  const value = useMemo(
    () => ({ token, profile, loading, login, register, logout }),
    [token, profile, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
