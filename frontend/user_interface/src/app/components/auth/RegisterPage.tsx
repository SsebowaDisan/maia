import { useState } from "react";
import { useAuthStore } from "../../stores/authStore";

type Props = {
  onSwitchToLogin: () => void;
};

async function apiRegister(body: {
  company_name: string;
  full_name: string;
  email: string;
  password: string;
}) {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(data.detail || "Registration failed.");
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

export function RegisterPage({ onSwitchToLogin }: Props) {
  const { setTokens, setUser } = useAuthStore();
  const [companyName, setCompanyName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const tokens = await apiRegister({
        company_name: companyName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
      const user = await apiGetMe(tokens.access_token);
      setTokens(tokens.access_token, tokens.refresh_token);
      setUser(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f5f5f7]">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-sm border border-black/[0.06]">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">Maia</h1>
          <p className="mt-1 text-[13px] text-[#6e6e73]">Create your company workspace</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">
              Company name
            </label>
            <input
              type="text"
              required
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white transition-colors"
              placeholder="Acme Corp"
            />
          </div>

          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">
              Your name
            </label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white transition-colors"
              placeholder="Jane Smith"
            />
          </div>

          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">
              Work email
            </label>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white transition-colors"
              placeholder="jane@acme.com"
            />
          </div>

          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">
              Password
            </label>
            <input
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white transition-colors"
              placeholder="Min. 8 characters"
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
            {loading ? "Creating workspace…" : "Create workspace"}
          </button>
        </form>

        <p className="mt-4 text-center text-[11px] text-[#8e8e93] leading-relaxed">
          By creating an account you agree to our Terms of Service.
        </p>

        <p className="mt-4 text-center text-[12px] text-[#6e6e73]">
          Already have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="font-medium text-[#1d1d1f] hover:underline"
          >
            Sign in
          </button>
        </p>
      </div>
    </div>
  );
}
