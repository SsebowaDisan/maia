import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

import {
  deactivateWorkspaceUser,
  inviteWorkspaceUser,
  listWorkspaceUsers,
  updateWorkspaceUser,
  type InviteWorkspaceUserResponse,
  type ManagedUser,
  type UserRole,
} from "../../../../api/client";
import { useAuthStore } from "../../../stores/authStore";
import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip } from "../ui/StatusChip";

type AccessSettingsProps = {
  onStatusMessage?: (text: string) => void;
};

function roleLabel(role: string): string {
  const normalized = String(role || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ");
  if (normalized === "super admin" || normalized === "superadmin") return "Super admin";
  if (normalized === "org admin" || normalized === "admin") return "Admin";
  if (normalized === "org user" || normalized === "user") return "User";
  return normalized || "Unknown";
}

type RoleSelectProps = {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
  align?: "start" | "end";
};

function RoleSelect({
  value,
  options,
  onChange,
  disabled = false,
  className = "",
  align = "start",
}: RoleSelectProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const normalizedOptions = options.map((option) => String(option));
  const selected = normalizedOptions.includes(String(value))
    ? String(value)
    : (normalizedOptions[0] ?? "");

  useEffect(() => {
    if (!open) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      const root = rootRef.current;
      if (!root) return;
      if (!root.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex w-full items-center justify-between gap-2 rounded-xl border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Role: ${roleLabel(selected)}`}
      >
        <span>{roleLabel(selected)}</span>
        <ChevronDown className="h-3.5 w-3.5 text-[#6e6e73]" />
      </button>
      {open ? (
        <div
          role="menu"
          className={`absolute z-[120] mt-1 min-w-full rounded-xl border border-[#d2d2d7] bg-white p-1 shadow-[0_10px_20px_rgba(0,0,0,0.08)] ${align === "end" ? "right-0" : "left-0"}`}
        >
          {normalizedOptions.map((option) => {
            const isSelected = option === selected;
            return (
              <button
                key={option}
                type="button"
                role="menuitemradio"
                aria-checked={isSelected}
                onClick={() => {
                  onChange(option);
                  setOpen(false);
                }}
                className={`flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] text-[#1d1d1f] hover:bg-[#f2f2f5] ${isSelected ? "bg-[#f5f5f7]" : ""}`}
              >
                {roleLabel(option)}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function AccessSettings({ onStatusMessage }: AccessSettingsProps) {
  const currentUser = useAuthStore((state) => state.user);
  const isOrgAdmin = useAuthStore((state) => state.isOrgAdmin());
  const isSuperAdmin = useAuthStore((state) => state.isSuperAdmin());

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [savingByUserId, setSavingByUserId] = useState<Record<string, boolean>>({});
  const [draftRoleByUserId, setDraftRoleByUserId] = useState<Record<string, string>>({});
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteFullName, setInviteFullName] = useState("");
  const [inviteRole, setInviteRole] = useState<UserRole>("org_user");
  const [inviteTempPassword, setInviteTempPassword] = useState("");
  const [inviteSendEmail, setInviteSendEmail] = useState(true);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteResult, setInviteResult] = useState<InviteWorkspaceUserResponse | null>(null);
  const [copyStatus, setCopyStatus] = useState("");

  const isAdminUser = Boolean(isOrgAdmin);

  const canEditRoles = isAdminUser;

  const resolvedCurrentUser = useMemo(() => {
    const superAdminFromUsers = users.find(
      (row) => String(row.role || "").trim().toLowerCase() === "super_admin",
    );
    const activeMatch = currentUser
      ? users.find((row) => row.id === currentUser.id && row.is_active)
      : null;

    if (activeMatch) {
      return {
        id: activeMatch.id,
        email: activeMatch.email,
        full_name: activeMatch.full_name,
        role: activeMatch.role as "super_admin" | "org_admin" | "org_user",
        tenant_id: activeMatch.tenant_id,
        is_active: activeMatch.is_active,
      };
    }
    if (superAdminFromUsers) {
      return {
        id: superAdminFromUsers.id,
        email: superAdminFromUsers.email,
        full_name: superAdminFromUsers.full_name,
        role: superAdminFromUsers.role as "super_admin" | "org_admin" | "org_user",
        tenant_id: superAdminFromUsers.tenant_id,
        is_active: superAdminFromUsers.is_active,
      };
    }
    return currentUser;
  }, [currentUser, users]);

  const inviteRoleOptions = isSuperAdmin
    ? (["org_user", "org_admin", "super_admin"] as const)
    : (["org_user", "org_admin"] as const);

  const setBusy = (userId: string, value: boolean) => {
    setSavingByUserId((prev) => ({ ...prev, [userId]: value }));
  };

  const loadUsers = async () => {
    if (!isAdminUser) {
      setUsers([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const rows = await listWorkspaceUsers();
      setUsers(rows);
      setDraftRoleByUserId((prev) => {
        const next = { ...prev };
        for (const row of rows) {
          next[row.id] = String(row.role || "org_user");
        }
        return next;
      });
    } catch (err) {
      const message = String(err || "Failed to load users.");
      setError(message);
      onStatusMessage?.(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers();
  }, [isAdminUser]);

  const handleInvite = async () => {
    if (!isAdminUser) return;
    const email = inviteEmail.trim();
    const fullName = inviteFullName.trim();
    const temporaryPassword = inviteTempPassword.trim();
    if (!email) {
      setError("Invite email is required.");
      return;
    }
    if (temporaryPassword && temporaryPassword.length < 8) {
      setError("Temporary password must be at least 8 characters if provided.");
      return;
    }
    setInviteLoading(true);
    setError("");
    setCopyStatus("");
    try {
      const result = await inviteWorkspaceUser({
        email,
        full_name: fullName,
        role: inviteRole,
        temporary_password: temporaryPassword || undefined,
        send_invite_email: inviteSendEmail,
      });
      setInviteResult(result);
      setInviteEmail("");
      setInviteFullName("");
      setInviteTempPassword("");
      if (result.email_sent) {
        onStatusMessage?.(`User invited and email sent: ${email}`);
      } else if (result.email_error) {
        onStatusMessage?.(`User invited. Link ready to copy. Email not sent: ${result.email_error}`);
      } else {
        onStatusMessage?.(`User invited. Link ready to copy: ${email}`);
      }
      await loadUsers();
    } catch (err) {
      const message = String(err || "Invite failed.");
      setError(message);
      onStatusMessage?.(message);
    } finally {
      setInviteLoading(false);
    }
  };

  const handleCopyInviteLink = async () => {
    const inviteLink = String(inviteResult?.invite_link || "").trim();
    if (!inviteLink) return;
    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopyStatus("Invite link copied.");
    } catch {
      setCopyStatus("Copy failed. Select and copy manually.");
    }
  };

  const handleSaveRole = async (target: ManagedUser) => {
    if (!canEditRoles) return;
    const nextRole = String(draftRoleByUserId[target.id] || target.role || "").trim();
    if (!nextRole || nextRole === String(target.role || "").trim()) {
      return;
    }
    setBusy(target.id, true);
    try {
      const updated = await updateWorkspaceUser(target.id, { role: nextRole });
      setUsers((prev) => prev.map((row) => (row.id === target.id ? updated : row)));
      onStatusMessage?.(`Updated role for ${updated.email}`);
    } catch (err) {
      const message = String(err || "Failed to update role.");
      setError(message);
      onStatusMessage?.(message);
    } finally {
      setBusy(target.id, false);
    }
  };

  const handleDeactivate = async (target: ManagedUser) => {
    if (!isAdminUser) return;
    if (target.id === resolvedCurrentUser?.id) {
      setError("You cannot deactivate your own account.");
      return;
    }
    setBusy(target.id, true);
    try {
      await deactivateWorkspaceUser(target.id);
      setUsers((prev) => prev.filter((row) => row.id !== target.id));
      onStatusMessage?.(`Deactivated user: ${target.email}`);
    } catch (err) {
      const message = String(err || "Failed to deactivate user.");
      setError(message);
      onStatusMessage?.(message);
    } finally {
      setBusy(target.id, false);
    }
  };

  return (
    <>
      <SettingsSection
        title="Access control"
        subtitle="Workspace roles and permissions for admins and users."
      >
        <SettingsRow
          title="Your role"
          description={resolvedCurrentUser ? `${resolvedCurrentUser.email}` : "Not signed in"}
          right={
            <StatusChip
              label={resolvedCurrentUser ? roleLabel(resolvedCurrentUser.role) : "Unknown"}
              tone={isAdminUser ? "success" : "neutral"}
            />
          }
        />
        <SettingsRow
          title="Permission scope"
          description={
            isAdminUser
              ? "You can invite users and manage workspace access."
              : "You have member access. Ask an admin to manage users or access policies."
          }
          right={<StatusChip label={isAdminUser ? "Admin" : "Member"} tone={isAdminUser ? "success" : "neutral"} />}
          noDivider
        />
      </SettingsSection>

      <SettingsSection
        title="Invite user"
        subtitle="Create a user, generate a secure invite link, and optionally send email."
      >
        <SettingsRow
          title="New user"
          description={isAdminUser ? "Invite a teammate and share their onboarding link." : "Admin access required."}
          noDivider
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <input
              type="email"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="user@company.com"
              disabled={!isAdminUser || inviteLoading}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f9f9fb] px-3 py-2 text-[13px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] disabled:opacity-60"
            />
            <input
              type="text"
              value={inviteFullName}
              onChange={(event) => setInviteFullName(event.target.value)}
              placeholder="Full name (optional)"
              disabled={!isAdminUser || inviteLoading}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f9f9fb] px-3 py-2 text-[13px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] disabled:opacity-60"
            />
            <RoleSelect
              value={inviteRole}
              options={inviteRoleOptions}
              onChange={(next) => setInviteRole(next as UserRole)}
              disabled={!isAdminUser || inviteLoading}
              className="w-full py-2 text-[13px]"
            />
            <input
              type="password"
              value={inviteTempPassword}
              onChange={(event) => setInviteTempPassword(event.target.value)}
              placeholder="Temporary password (optional)"
              disabled={!isAdminUser || inviteLoading}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#f9f9fb] px-3 py-2 text-[13px] text-[#1d1d1f] outline-none focus:border-[#1d1d1f] disabled:opacity-60"
            />
          </div>
          <label className="mt-3 inline-flex items-center gap-2 text-[12px] text-[#1d1d1f]">
            <input
              type="checkbox"
              checked={inviteSendEmail}
              onChange={(event) => setInviteSendEmail(event.target.checked)}
              disabled={!isAdminUser || inviteLoading}
            />
            Send invite link by email automatically
          </label>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[11px] text-[#6e6e73]">
              The invited user opens the link, sets their password once, and keeps access until deactivated.
            </p>
            <button
              type="button"
              onClick={() => void handleInvite()}
              disabled={!isAdminUser || inviteLoading}
              className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-60"
            >
              {inviteLoading ? "Inviting..." : "Invite user"}
            </button>
          </div>
          {inviteResult ? (
            <div className="mt-3 rounded-xl border border-[#d2d2d7] bg-[#ffffff] p-3">
              <p className="text-[12px] font-semibold text-[#1d1d1f]">Invite link</p>
              <input
                type="text"
                readOnly
                value={inviteResult.invite_link}
                className="mt-2 w-full rounded-lg border border-[#d2d2d7] bg-[#f9f9fb] px-2 py-1.5 text-[12px] text-[#1d1d1f]"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleCopyInviteLink()}
                  className="rounded-lg border border-[#d2d2d7] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
                >
                  Copy link
                </button>
                <a
                  href={`mailto:${encodeURIComponent(inviteResult.user.email)}?subject=${encodeURIComponent("Your Maia invite link")}&body=${encodeURIComponent(`Use this link to join Maia:\\n\\n${inviteResult.invite_link}`)}`}
                  className="rounded-lg border border-[#d2d2d7] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
                >
                  Open email draft
                </a>
                <span className="text-[11px] text-[#6e6e73]">
                  Expires: {new Date(inviteResult.invite_expires_at).toLocaleString()}
                </span>
              </div>
              {inviteResult.email_sent ? (
                <p className="mt-2 text-[12px] text-[#1f7a3d]">Invite email sent.</p>
              ) : null}
              {inviteResult.email_error ? (
                <p className="mt-2 text-[12px] text-[#8c2f2f]">Email send failed: {inviteResult.email_error}</p>
              ) : null}
              {copyStatus ? <p className="mt-1 text-[11px] text-[#6e6e73]">{copyStatus}</p> : null}
            </div>
          ) : null}
          {error ? <p className="mt-2 text-[12px] text-[#8c2f2f]">{error}</p> : null}
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Users"
        subtitle="Review and manage current workspace members."
        actions={
          <button
            type="button"
            onClick={() => void loadUsers()}
            disabled={loading}
            className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-60"
          >
            {loading ? "Refreshing..." : "Refresh users"}
          </button>
        }
      >
        {users.length === 0 ? (
          <SettingsRow
            title={loading ? "Loading users..." : "No users found"}
            description={loading ? "Fetching current workspace users." : "Invite users to populate this list."}
            noDivider
          />
        ) : (
          users.map((row, index) => {
            const disabled = Boolean(savingByUserId[row.id]);
            const isSelf = row.id === resolvedCurrentUser?.id;
            return (
              <SettingsRow
                key={row.id}
                title={row.full_name || row.email}
                description={row.email}
                noDivider={index === users.length - 1}
                right={
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusChip label={row.is_active ? "Active" : "Inactive"} tone={row.is_active ? "success" : "neutral"} />
                    <RoleSelect
                      value={String(draftRoleByUserId[row.id] || row.role || "org_user")}
                      options={inviteRoleOptions}
                      onChange={(next) =>
                        setDraftRoleByUserId((prev) => ({ ...prev, [row.id]: next }))
                      }
                      disabled={!canEditRoles || disabled}
                      className="min-w-[132px]"
                      align="end"
                    />
                    <button
                      type="button"
                      onClick={() => void handleSaveRole(row)}
                      disabled={!canEditRoles || disabled}
                      className="rounded-xl border border-[#d2d2d7] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-60"
                    >
                      Save role
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeactivate(row)}
                      disabled={!isAdminUser || disabled || isSelf}
                      className="rounded-xl border border-[#e0c4c4] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#7a3030] hover:bg-[#fdf6f6] disabled:opacity-60"
                    >
                      Deactivate
                    </button>
                  </div>
                }
              />
            );
          })
        )}
      </SettingsSection>
    </>
  );
}
