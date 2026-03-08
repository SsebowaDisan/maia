import { useCallback, useRef, useState } from "react";

export type DeletePromptArgs = {
  title: string;
  description: string;
  confirmLabel?: string;
  action: () => Promise<void> | void;
};

export function useDeletePromptController() {
  const [deletePromptOpen, setDeletePromptOpen] = useState(false);
  const [deletePromptTitle, setDeletePromptTitle] = useState("Delete item");
  const [deletePromptDescription, setDeletePromptDescription] = useState("");
  const [deletePromptConfirmLabel, setDeletePromptConfirmLabel] = useState("Delete");
  const [deletePromptInput, setDeletePromptInput] = useState("");
  const [deletePromptBusy, setDeletePromptBusy] = useState(false);
  const [deletePromptError, setDeletePromptError] = useState("");
  const deletePromptActionRef = useRef<(() => Promise<void>) | null>(null);

  const closeDeletePrompt = useCallback(() => {
    if (deletePromptBusy) {
      return;
    }
    setDeletePromptOpen(false);
    setDeletePromptInput("");
    setDeletePromptError("");
    setDeletePromptConfirmLabel("Delete");
    deletePromptActionRef.current = null;
  }, [deletePromptBusy]);

  const openDeletePrompt = useCallback((args: DeletePromptArgs) => {
    setDeletePromptTitle(args.title);
    setDeletePromptDescription(args.description);
    setDeletePromptConfirmLabel(String(args.confirmLabel || "Delete"));
    setDeletePromptInput("");
    setDeletePromptError("");
    deletePromptActionRef.current = async () => {
      await Promise.resolve(args.action());
    };
    setDeletePromptOpen(true);
  }, []);

  const confirmDeletePrompt = useCallback(async () => {
    if (deletePromptBusy) {
      return;
    }
    if (deletePromptInput.trim().toLowerCase() !== "delete") {
      setDeletePromptError('Type "delete" to confirm.');
      return;
    }
    const action = deletePromptActionRef.current;
    if (!action) {
      closeDeletePrompt();
      return;
    }
    setDeletePromptBusy(true);
    setDeletePromptError("");
    try {
      await action();
      setDeletePromptOpen(false);
      setDeletePromptInput("");
      setDeletePromptError("");
      setDeletePromptConfirmLabel("Delete");
      deletePromptActionRef.current = null;
    } catch (error) {
      setDeletePromptError(`Delete failed: ${String(error)}`);
    } finally {
      setDeletePromptBusy(false);
    }
  }, [closeDeletePrompt, deletePromptBusy, deletePromptInput]);

  return {
    deletePromptOpen,
    deletePromptTitle,
    deletePromptDescription,
    deletePromptConfirmLabel,
    deletePromptInput,
    deletePromptBusy,
    deletePromptError,
    setDeletePromptInput,
    setDeletePromptError,
    openDeletePrompt,
    closeDeletePrompt,
    confirmDeletePrompt,
  };
}
