import type { Dispatch, SetStateAction } from "react";
import type { FileGroupRecord, FileRecord } from "../../../../api/client";
import type { SidebarProject } from "../../../appShell/types";
import type { ChatAttachment } from "../../../types";
import type { ComposerAttachment } from "../types";

type SetAttachments = Dispatch<SetStateAction<ComposerAttachment[]>>;

function mapTurnAttachments(turnAttachments?: ChatAttachment[]): ComposerAttachment[] {
  return (turnAttachments || []).map((attachment, idx) => ({
    id: `compose-${Date.now()}-${idx}-${attachment.name}`,
    name: attachment.name,
    status: "indexed" as const,
    fileId: attachment.fileId,
    kind: attachment.fileId ? ("file" as const) : undefined,
    entityId: attachment.fileId || undefined,
  }));
}

function createDocumentAttachment(file: { id: string; name: string }, fallbackIdPrefix = "doc"): ComposerAttachment {
  return {
    id: `${fallbackIdPrefix}-${file.id}-${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
    name: file.name,
    status: "indexed",
    fileId: file.id,
    kind: "file",
    entityId: file.id,
  };
}

function attachDocumentById({
  fileId,
  availableDocuments,
  setAttachments,
  showActionStatus,
}: {
  fileId: string;
  availableDocuments: FileRecord[];
  setAttachments: SetAttachments;
  showActionStatus: (text: string) => void;
}) {
  const target = availableDocuments.find((item) => item.id === fileId);
  if (!target) {
    showActionStatus("Document not found.");
    return;
  }
  let added = false;
  setAttachments((previous) => {
    if (previous.some((item) => item.fileId && item.fileId === target.id)) {
      return previous;
    }
    added = true;
    return [...previous, createDocumentAttachment(target)];
  });
  if (!added) {
    showActionStatus(`"${target.name}" is already attached.`);
    return;
  }
  showActionStatus(`Attached "${target.name}".`);
}

function attachGroupById({
  groupId,
  availableGroups,
  availableDocuments,
  setAttachments,
  showActionStatus,
}: {
  groupId: string;
  availableGroups: FileGroupRecord[];
  availableDocuments: FileRecord[];
  setAttachments: SetAttachments;
  showActionStatus: (text: string) => void;
}) {
  const group = availableGroups.find((item) => item.id === groupId);
  if (!group) {
    showActionStatus("Group not found.");
    return;
  }

  const docsById = new Map(availableDocuments.map((item) => [item.id, item]));
  const groupDocs = Array.from(new Set(group.file_ids || []))
    .map((fileId) => docsById.get(fileId))
    .filter((item): item is NonNullable<typeof item> => Boolean(item));
  if (!groupDocs.length) {
    showActionStatus(`"${group.name}" has no available documents.`);
    return;
  }

  const attachLimit = 40;
  const slicedDocs = groupDocs.slice(0, attachLimit);
  let addedCount = 0;
  setAttachments((previous) => {
    const existingFileIds = new Set(previous.map((item) => String(item.fileId || "").trim()).filter(Boolean));
    const next = [...previous];
    for (const doc of slicedDocs) {
      if (existingFileIds.has(doc.id)) {
        continue;
      }
      next.push(createDocumentAttachment(doc, "group-doc"));
      existingFileIds.add(doc.id);
      addedCount += 1;
    }
    return next;
  });

  if (!addedCount) {
    showActionStatus(`All documents from "${group.name}" are already attached.`);
    return;
  }
  const remaining = groupDocs.length - slicedDocs.length;
  if (remaining > 0) {
    showActionStatus(
      `Attached ${addedCount} docs from "${group.name}" (limit ${attachLimit}, ${remaining} not added).`,
    );
    return;
  }
  showActionStatus(`Attached ${addedCount} docs from "${group.name}".`);
}

function attachProjectById({
  projectId,
  availableProjects,
  setAttachments,
  showActionStatus,
}: {
  projectId: string;
  availableProjects: SidebarProject[];
  setAttachments: SetAttachments;
  showActionStatus: (text: string) => void;
}) {
  const project = availableProjects.find((item) => item.id === projectId);
  if (!project) {
    showActionStatus("Project not found.");
    return;
  }
  const projectEntityId = `project:${project.id}`;
  let added = false;
  setAttachments((previous) => {
    if (
      previous.some(
        (item) => item.kind === "project" && String(item.entityId || "").trim() === projectEntityId,
      )
    ) {
      return previous;
    }
    added = true;
    return [
      ...previous,
      {
        id: `project-${project.id}-${Date.now()}`,
        name: `Project: ${project.name}`,
        status: "indexed",
        kind: "project",
        entityId: projectEntityId,
      },
    ];
  });
  if (!added) {
    showActionStatus(`"${project.name}" is already attached.`);
    return;
  }
  showActionStatus(`Attached project "${project.name}".`);
}

export { attachDocumentById, attachGroupById, attachProjectById, mapTurnAttachments };
