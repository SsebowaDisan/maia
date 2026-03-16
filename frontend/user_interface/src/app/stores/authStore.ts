/**
 * Auth store — manages JWT tokens and current user profile.
 *
 * Tokens are persisted to localStorage so the session survives page reloads.
 * The access token is short-lived (60 min by default); the refresh token is
 * long-lived (30 days).  The store exposes helpers used by the API client to
 * inject the Bearer token into every request.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type UserRole = "super_admin" | "org_admin" | "org_user";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  tenant_id: string | null;
  is_active: boolean;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;

  // Actions
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: AuthUser) => void;
  logout: () => void;

  // Derived helpers
  isAuthenticated: () => boolean;
  isOrgAdmin: () => boolean;
  isSuperAdmin: () => boolean;
  getBearerHeader: () => Record<string, string>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      setTokens: (access, refresh) => set({ accessToken: access, refreshToken: refresh }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),

      isAuthenticated: () => Boolean(get().accessToken && get().user),
      isOrgAdmin: () => {
        const role = get().user?.role;
        return role === "org_admin" || role === "super_admin";
      },
      isSuperAdmin: () => get().user?.role === "super_admin",

      getBearerHeader: () => {
        const token = get().accessToken;
        return token ? { Authorization: `Bearer ${token}` } : {};
      },
    }),
    {
      name: "maia.auth",
      // Only persist tokens + user — do not persist derived methods
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    },
  ),
);
