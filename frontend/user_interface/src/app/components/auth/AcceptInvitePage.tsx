import { useEffect, useMemo, useState } from "react";
import { useAuthStore } from "../../stores/authStore";

type InvitePreview = {
  email: string;
  full_name: string;
  role: string;
  expires_at: string;
};

type AcceptInviteResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    role: "super_admin" | "org_admin" | "org_user";
    tenant_id: string | null;
    is_active: boolean;
  };
};

function roleLabel(role: string): string {
  const normalized = String(role || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ");
  if (normalized === "super admin" || normalized === "superadmin") return "Super admin";
  if (normalized === "org admin" || normalized === "admin") return "Admin";
  if (normalized === "org user" || normalized === "user") return "User";
  return String(role || "").trim() || "Unknown";
}

async function apiPreviewInvite(token: string): Promise<InvitePreview> {
  const response = await fetch(`/api/auth/invite/preview?token=${encodeURIComponent(token)}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || "Invite is invalid or expired.");
  }
  return response.json() as Promise<InvitePreview>;
}

async function apiAcceptInvite(params: { token: string; password: string; full_name?: string }): Promise<AcceptInviteResponse> {
  const response = await fetch("/api/auth/invite/accept", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || "Unable to accept invite.");
  }
  return response.json() as Promise<AcceptInviteResponse>;
}

export function AcceptInvitePage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const token = String(query.get("token") || "").trim();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const { setTokens, setUser } = useAuthStore();

  useEffect(() => {
    if (!token) {
      setError("Missing invite token.");
      return;
    }
    setLoadingPreview(true);
    setError("");
    apiPreviewInvite(token)
      .then((data) => {
        setPreview(data);
        if (data.full_name) {
          setFullName(data.full_name);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Invite is invalid or expired.");
      })
      .finally(() => setLoadingPreview(false));
  }, [token]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await apiAcceptInvite({
        token,
        password,
        full_name: fullName.trim() || undefined,
      });
      setTokens(result.access_token, result.refresh_token);
      setUser(result.user);
      window.history.replaceState({}, "", "/");
      window.location.assign("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to accept invite.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f5f5f7] px-4">
      <div className="w-full max-w-md rounded-2xl border border-black/[0.06] bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">Accept invitation</h1>
        <p className="mt-1 text-[13px] text-[#6e6e73]">
          {loadingPreview
            ? "Validating invite..."
            : preview
              ? `Join as ${preview.email}`
              : "Use your invite link to continue."}
        </p>

        {preview ? (
          <p className="mt-2 text-[12px] text-[#6e6e73]">
            Role: {roleLabel(preview.role)} • Expires: {new Date(preview.expires_at).toLocaleString()}
          </p>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">Full name</label>
            <input
              type="text"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white"
              placeholder="Your name"
              disabled={submitting || !preview}
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">Password</label>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white"
              placeholder="At least 8 characters"
              disabled={submitting || !preview}
            />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium text-[#3a3a3c]">Confirm password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-[14px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] focus:bg-white"
              placeholder="Repeat password"
              disabled={submitting || !preview}
            />
          </div>

          {error ? (
            <p className="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-[12px] text-red-600">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !preview}
            className="w-full rounded-xl bg-[#1d1d1f] py-2.5 text-[14px] font-medium text-white transition-colors hover:bg-[#3a3a3c] disabled:opacity-50"
          >
            {submitting ? "Activating..." : "Activate account"}
          </button>
        </form>
      </div>
    </div>
  );
}
