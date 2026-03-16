import { useState } from "react";
import { useAuthStore } from "../../stores/authStore";

type Props = {
  onSwitchToRegister: () => void;
};

async function apiLogin(email: string, password: string) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || "Login failed.");
  }
  return res.json() as Promise<{ access_token: string; refresh_token: string }>;
}

async function apiGetMe(token: string) {
  const res = await fetch("/api/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch user profile.");
  return res.json();
}

export function LoginPage({ onSwitchToRegister }: Props) {
  const { setTokens, setUser } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const tokens = await apiLogin(email.trim(), password);
      const user = await apiGetMe(tokens.access_token);
      setTokens(tokens.access_token, tokens.refresh_token);
      setUser(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f5f5f7]">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-sm border border-black/[0.06]">
        {/* Logo / wordmark */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">Maia</h1>
          <p className="mt-1 text-[13px] text-[#6e6e73]">Sign in to your workspace</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">
              Email
            </label>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white transition-colors"
              placeholder="you@company.com"
            />
          </div>

          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">
              Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white transition-colors"
              placeholder="••••••••"
            />
          </div>

          {error ? (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-[12px] text-red-600 border border-red-100">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-[#1d1d1f] py-2.5 text-[14px] font-medium text-white transition-colors hover:bg-[#3a3a3c] disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-[12px] text-[#6e6e73]">
          New company?{" "}
          <button
            type="button"
            onClick={onSwitchToRegister}
            className="font-medium text-[#1d1d1f] hover:underline"
          >
            Create an account
          </button>
        </p>
      </div>
    </div>
  );
}
