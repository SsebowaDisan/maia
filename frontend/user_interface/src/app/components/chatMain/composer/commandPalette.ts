import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from "react";
import type { FileGroupRecord, FileRecord } from "../../../../api/client";
import type { SidebarProject } from "../../../appShell/types";

const MAX_COMMAND_OPTIONS = 8;

type CommandTrigger = "document" | "group" | "project";
type CommandOption = {
  id: string;
  label: string;
  subtitle?: string;
};
type CommandQueryState = {
  trigger: CommandTrigger;
  query: string;
  tokenStart: number;
  caret: number;
};

const TRIGGER_MAP: Record<string, CommandTrigger> = {
  "@": "document",
  "#": "group",
  "/": "project",
};

function resolveCommandQuery(text: string, caret: number): CommandQueryState | null {
  const safeCaret = Math.max(0, Math.min(caret, text.length));
  const beforeCaret = text.slice(0, safeCaret);
  const match = /(^|\s)([@#/])([^\s@#/]*)$/.exec(beforeCaret);
  if (!match) {
    return null;
  }
  const triggerChar = String(match[2] || "");
  const trigger = TRIGGER_MAP[triggerChar];
  if (!trigger) {
    return null;
  }
  const query = String(match[3] || "");
  const tokenStart = safeCaret - query.length - 1;
  if (tokenStart < 0) {
    return null;
  }
  return {
    trigger,
    query,
    tokenStart,
    caret: safeCaret,
  };
}

type UseComposerCommandPaletteParams = {
  message: string;
  setMessage: (value: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  documentOptions: FileRecord[];
  groupOptions: FileGroupRecord[];
  projectOptions: SidebarProject[];
  onAttachDocument: (documentId: string) => void;
  onAttachGroup: (groupId: string) => void;
  onAttachProject: (projectId: string) => void;
  onSubmit: () => void;
};

function useComposerCommandPalette({
  message,
  setMessage,
  textareaRef,
  documentOptions,
  groupOptions,
  projectOptions,
  onAttachDocument,
  onAttachGroup,
  onAttachProject,
  onSubmit,
}: UseComposerCommandPaletteParams) {
  const [commandQuery, setCommandQuery] = useState<CommandQueryState | null>(null);
  const [commandActiveIndex, setCommandActiveIndex] = useState(0);

  const commandOptions = useMemo<CommandOption[]>(() => {
    if (!commandQuery) {
      return [];
    }
    const normalizedQuery = commandQuery.query.trim().toLowerCase();
    const includeOption = (value: string) => !normalizedQuery || value.toLowerCase().includes(normalizedQuery);

    if (commandQuery.trigger === "document") {
      return documentOptions
        .filter((item) => includeOption(item.name))
        .slice(0, MAX_COMMAND_OPTIONS)
        .map((item) => ({
          id: item.id,
          label: item.name,
          subtitle: "Document",
        }));
    }
    if (commandQuery.trigger === "group") {
      return groupOptions
        .filter((item) => includeOption(item.name))
        .slice(0, MAX_COMMAND_OPTIONS)
        .map((item) => ({
          id: item.id,
          label: item.name,
          subtitle: `${(item.file_ids || []).length} docs`,
        }));
    }
    return projectOptions
      .filter((item) => includeOption(item.name))
      .slice(0, MAX_COMMAND_OPTIONS)
      .map((item) => ({
        id: item.id,
        label: item.name,
        subtitle: "Project",
      }));
  }, [commandQuery, documentOptions, groupOptions, projectOptions]);

  const updateCommandQuery = useCallback((nextText: string, caret: number) => {
    const next = resolveCommandQuery(nextText, caret);
    setCommandQuery(next);
    setCommandActiveIndex(0);
  }, []);

  const removeCommandToken = useCallback((query: CommandQueryState) => {
    const before = message.slice(0, query.tokenStart).replace(/\s+$/, " ");
    const after = message.slice(query.caret).replace(/^\s+/, "");
    const nextMessage = `${before}${after}`.replace(/\s{3,}/g, " ").trimStart();
    setMessage(nextMessage);
    window.requestAnimationFrame(() => {
      const element = textareaRef.current;
      if (!element) {
        return;
      }
      const caretPosition = Math.max(0, Math.min(before.length, nextMessage.length));
      element.focus();
      element.setSelectionRange(caretPosition, caretPosition);
    });
    setCommandQuery(null);
    setCommandActiveIndex(0);
  }, [message, setMessage, textareaRef]);

  const attachFromCommand = useCallback((option: CommandOption) => {
    if (!commandQuery) {
      return;
    }
    if (commandQuery.trigger === "document") {
      onAttachDocument(option.id);
    } else if (commandQuery.trigger === "group") {
      onAttachGroup(option.id);
    } else {
      onAttachProject(option.id);
    }
    removeCommandToken(commandQuery);
  }, [commandQuery, onAttachDocument, onAttachGroup, onAttachProject, removeCommandToken]);

  const handleMessageChange = useCallback((event: ChangeEvent<HTMLTextAreaElement>) => {
    const nextMessage = event.target.value;
    setMessage(nextMessage);
    updateCommandQuery(nextMessage, event.target.selectionStart ?? nextMessage.length);
  }, [setMessage, updateCommandQuery]);

  const syncCommandQueryFromTextarea = useCallback(() => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    updateCommandQuery(element.value, element.selectionStart ?? element.value.length);
  }, [textareaRef, updateCommandQuery]);

  const handleComposerKeyDown = useCallback((event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (commandQuery && commandOptions.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setCommandActiveIndex((previous) => (previous + 1) % commandOptions.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setCommandActiveIndex((previous) => (previous - 1 + commandOptions.length) % commandOptions.length);
        return;
      }
      if (event.key === "Tab" || event.key === "Enter") {
        event.preventDefault();
        const option = commandOptions[Math.max(0, Math.min(commandActiveIndex, commandOptions.length - 1))];
        if (option) {
          attachFromCommand(option);
        }
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setCommandQuery(null);
        setCommandActiveIndex(0);
        return;
      }
    }
    if (event.key !== "Enter" || event.nativeEvent.isComposing || event.shiftKey) {
      return;
    }
    event.preventDefault();
    onSubmit();
  }, [attachFromCommand, commandActiveIndex, commandOptions, commandQuery, onSubmit]);

  useEffect(() => {
    if (!commandOptions.length) {
      setCommandActiveIndex(0);
      return;
    }
    setCommandActiveIndex((previous) => Math.max(0, Math.min(previous, commandOptions.length - 1)));
  }, [commandOptions.length]);

  useEffect(() => {
    if (message.length === 0 && commandQuery) {
      setCommandQuery(null);
      setCommandActiveIndex(0);
    }
  }, [commandQuery, message]);

  return {
    commandActiveIndex,
    commandOptions,
    commandQuery,
    handleComposerKeyDown,
    handleMessageChange,
    selectCommandOption: attachFromCommand,
    syncCommandQueryFromTextarea,
  };
}

export type { CommandOption, CommandQueryState };
export { useComposerCommandPalette };
