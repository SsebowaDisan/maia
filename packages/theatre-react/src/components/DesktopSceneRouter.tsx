import React from "react";

export interface DesktopSceneRouterProps {
  isBrowserScene: boolean;
  isPdfScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isDocsScene: boolean;
  isSheetsScene: boolean;
  isSystemScene: boolean;
  hasApiScene?: boolean;
  hasSnapshotScene?: boolean;
  hasTeamChatScene?: boolean;
  browserScene?: React.ReactNode;
  teamChatScene?: React.ReactNode;
  apiScene?: React.ReactNode;
  snapshotScene?: React.ReactNode;
  emailScene?: React.ReactNode;
  sheetsScene?: React.ReactNode;
  pdfScene?: React.ReactNode;
  docsScene?: React.ReactNode;
  documentScene?: React.ReactNode;
  systemScene?: React.ReactNode;
  defaultScene: React.ReactNode;
}

export function DesktopSceneRouter({
  isBrowserScene,
  isPdfScene,
  isEmailScene,
  isDocumentScene,
  isDocsScene,
  isSheetsScene,
  isSystemScene,
  hasApiScene = false,
  hasSnapshotScene = false,
  hasTeamChatScene = false,
  browserScene = null,
  teamChatScene = null,
  apiScene = null,
  snapshotScene = null,
  emailScene = null,
  sheetsScene = null,
  pdfScene = null,
  docsScene = null,
  documentScene = null,
  systemScene = null,
  defaultScene,
}: DesktopSceneRouterProps) {
  if (isBrowserScene && !isPdfScene) {
    return <>{browserScene}</>;
  }

  if (hasTeamChatScene) {
    return <>{teamChatScene}</>;
  }

  if (hasApiScene && !isBrowserScene && !isDocumentScene && !isDocsScene && !isSheetsScene) {
    return <>{apiScene}</>;
  }

  if (
    hasSnapshotScene &&
    !isEmailScene &&
    !isDocumentScene &&
    !isDocsScene &&
    !isSheetsScene &&
    !isSystemScene
  ) {
    return <>{snapshotScene}</>;
  }

  if (isEmailScene) {
    return <>{emailScene}</>;
  }

  if (isSheetsScene) {
    return <>{sheetsScene}</>;
  }

  if (isPdfScene) {
    return <>{pdfScene}</>;
  }

  if (isDocsScene) {
    return <>{docsScene}</>;
  }

  if (isDocumentScene) {
    return <>{documentScene}</>;
  }

  if (isSystemScene) {
    return <>{systemScene}</>;
  }

  return <>{defaultScene}</>;
}
