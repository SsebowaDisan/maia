
  import { createRoot } from "react-dom/client";
  import "katex/dist/katex.min.css";
  import { Toaster } from "sonner";
  import App from "./app/App.tsx";
  import { AuthGate } from "./app/components/auth/AuthGate.tsx";
  import "./styles/index.css";

  // When MAIA_AUTH_DISABLED=true on the backend, set this env var to skip the
  // login gate in the frontend too (useful for local dev without accounts).
  const AUTH_DISABLED =
    (import.meta as { env?: Record<string, string> }).env?.VITE_AUTH_DISABLED === "true";

  createRoot(document.getElementById("root")!).render(
    <>
      <AuthGate authDisabled={AUTH_DISABLED}>
        <App />
      </AuthGate>
      <Toaster
        position="top-right"
        richColors={false}
        toastOptions={{
          style: {
            background: "#ffffff",
            border: "1px solid rgba(0, 0, 0, 0.08)",
            color: "#1d1d1f",
            borderRadius: "14px",
            boxShadow: "0 12px 28px rgba(0, 0, 0, 0.12)",
          },
        }}
      />
    </>,
  );
