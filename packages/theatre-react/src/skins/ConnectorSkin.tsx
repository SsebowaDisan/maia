/**
 * ConnectorSkin — wraps a Theatre surface with connector-specific branding.
 *
 * Usage:
 *   <ConnectorSkin connectorId="gmail" title="Composing report" status="in_progress">
 *     <EmailSurface surface={surface} />
 *   </ConnectorSkin>
 *
 * Renders a branded shell with the connector's colors, header with brand name,
 * and status pill — the child surface renders inside.
 */

import React from "react";
import { getConnectorSkin } from "./palettes";

export interface ConnectorSkinProps {
  /** Connector ID (e.g., "gmail", "slack", "github"). */
  connectorId: string;
  /** Title shown in the header. */
  title: string;
  /** Status pill text (e.g., "in_progress", "completed", "failed"). */
  status?: string;
  /** Optional subtitle under the title. */
  subtitle?: string;
  /** The surface component to render inside. */
  children: React.ReactNode;
  /** Additional CSS class for the outer container. */
  className?: string;
}

function statusTone(status: string): string {
  const n = String(status || "").trim().toLowerCase();
  if (n === "failed" || n === "error") return "border-[#f1b7b7] bg-[#fff5f5] text-[#9a2323]";
  if (n === "completed" || n === "success") return "border-[#bfd9c3] bg-[#f3fbf4] text-[#245437]";
  return "border-[#d2d2d7] bg-[#f5f5f7] text-[#3a3a3c]";
}

export function ConnectorSkin({ connectorId, title, status = "in_progress", subtitle, children, className = "" }: ConnectorSkinProps) {
  const { palette, descriptor } = getConnectorSkin(connectorId);

  return (
    <div className={`overflow-hidden rounded-2xl ${palette.shellGradient} ${className}`}>
      <div className={`mx-auto flex h-full w-full flex-col gap-3 rounded-2xl border ${palette.cardBorder} ${palette.cardBg} p-4 shadow-lg`}>
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className={`text-[11px] uppercase tracking-[0.11em] ${palette.textSecondary}`}>
              {descriptor.brand} — {descriptor.theatreLabel}
            </p>
            <h3 className={`mt-1 truncate text-[18px] font-semibold leading-tight ${palette.textPrimary}`}>
              {title || descriptor.actionVerb}
            </h3>
            {subtitle ? (
              <p className={`mt-1 text-[13px] ${palette.textSecondary}`}>{subtitle}</p>
            ) : null}
          </div>
          <div className={`shrink-0 rounded-full border px-3 py-1 text-[12px] font-semibold ${statusTone(status)}`}>
            {status}
          </div>
        </div>

        {/* Surface content */}
        <div className="flex-1 overflow-hidden rounded-xl">
          {children}
        </div>
      </div>
    </div>
  );
}