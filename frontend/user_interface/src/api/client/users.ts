import { request } from "./core";
import type { ManagedUser, UserRole } from "./types";

type InviteWorkspaceUserPayload = {
  email: string;
  full_name?: string;
  role?: UserRole | string;
  temporary_password?: string;
  send_invite_email?: boolean;
};

type UpdateWorkspaceUserPayload = {
  full_name?: string;
  role?: UserRole | string;
};

type InviteWorkspaceUserResponse = {
  user: ManagedUser;
  invite_link: string;
  invite_expires_at: string;
  email_sent: boolean;
  email_error?: string | null;
};

function listWorkspaceUsers() {
  return request<ManagedUser[]>("/api/users");
}

function inviteWorkspaceUser(payload: InviteWorkspaceUserPayload) {
  return request<InviteWorkspaceUserResponse>("/api/users/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function updateWorkspaceUser(userId: string, payload: UpdateWorkspaceUserPayload) {
  return request<ManagedUser>(`/api/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function deactivateWorkspaceUser(userId: string) {
  return request<void>(`/api/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

export {
  deactivateWorkspaceUser,
  inviteWorkspaceUser,
  listWorkspaceUsers,
  updateWorkspaceUser,
};

export type {
  InviteWorkspaceUserPayload,
  InviteWorkspaceUserResponse,
  UpdateWorkspaceUserPayload,
};
