
  import { createRoot } from "react-dom/client";
  import { Toaster } from "sonner";
  import App from "./app/App.tsx";
  import "./styles/index.css";

  createRoot(document.getElementById("root")!).render(
    <>
      <App />
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
  
