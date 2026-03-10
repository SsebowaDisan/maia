import { useEffect } from "react";

type PreviewTab = "browser" | "document" | "email" | "system";

function useManualPreviewTabOverride({
  streaming,
  setPreviewTab,
  setManualTabOverride,
}: {
  streaming: boolean;
  setPreviewTab: (tab: PreviewTab) => void;
  setManualTabOverride: (value: boolean) => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!streaming) {
        return;
      }
      const target = event.target as HTMLElement | null;
      const tagName = String(target?.tagName || "").toLowerCase();
      if (
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select" ||
        target?.isContentEditable
      ) {
        return;
      }
      if (event.key === "0") {
        setManualTabOverride(false);
        return;
      }
      const tabByKey: Record<string, PreviewTab> = {
        "1": "system",
        "2": "browser",
        "3": "document",
        "4": "email",
      };
      const manualTab = tabByKey[event.key];
      if (!manualTab) {
        return;
      }
      setPreviewTab(manualTab);
      setManualTabOverride(true);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setManualTabOverride, setPreviewTab, streaming]);
}

export { useManualPreviewTabOverride };

