/**
 * AuthGate — wraps the entire app and shows Login/Register when the user
 * is not authenticated.  Once tokens are stored in the auth store the
 * children (the main app shell) render normally.
 *
 * Dev mode: when MAIA_AUTH_DISABLED=true on the backend the app still works
 * without tokens — AuthGate shows the full app in that case too, because the
 * backend will accept the legacy X-User-Id header fallback.
 */
import { useState } from "react";
import { useAuthStore } from "../../stores/authStore";
import { AcceptInvitePage } from "./AcceptInvitePage";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";

type AuthView = "login" | "register";

interface Props {
  /** Whether backend auth enforcement is disabled (dev mode). */
  authDisabled?: boolean;
  children: React.ReactNode;
}

export function AuthGate({ authDisabled = false, children }: Props) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  const [view, setView] = useState<AuthView>("login");
  const path = typeof window !== "undefined" ? String(window.location.pathname || "") : "";

  if (path.startsWith("/accept-invite")) {
    return <AcceptInvitePage />;
  }

  // In dev/disabled mode skip the auth gate entirely
  if (authDisabled || isAuthenticated) {
    return <>{children}</>;
  }

  if (view === "register") {
    return <RegisterPage onSwitchToLogin={() => setView("login")} />;
  }

  return <LoginPage onSwitchToRegister={() => setView("register")} />;
}
