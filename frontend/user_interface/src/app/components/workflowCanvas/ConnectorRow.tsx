import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Eye, EyeOff, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  listConnectorCredentials,
  upsertConnectorCredentials,
} from "../../../api/client";
import { MANUAL_CONNECTOR_DEFINITIONS } from "../settings/connectorDefinitions";

function ConnectorRow({ connectorId, onSaved }: { connectorId: string; onSaved: () => void }) {
  const def = MANUAL_CONNECTOR_DEFINITIONS.find((d) => d.id === connectorId);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;
    listConnectorCredentials()
      .then((records) => {
        const match = records.find((r) => r.connector_id === connectorId);
        const hasValues = match && Object.values(match.values || {}).some((v) => String(v || "").length > 0);
        setConnected(Boolean(hasValues) || !def || def.fields.length === 0);
      })
      .catch(() => setConnected(false));
  }, [connectorId, def]);

  const label = def?.label || connectorId;
  const isPublic = !def || def.fields.length === 0;
  const statusDot = connected === null ? "bg-[#d0d5dd]" : connected ? "bg-[#17b26a]" : "bg-[#f04438]";

  const handleSave = async () => {
    setSaving(true);
    try {
      await upsertConnectorCredentials(connectorId, draft);
      setConnected(true);
      setExpanded(false);
      toast.success(`${label} connected`);
      onSaved();
    } catch {
      toast.error(`Failed to save ${label} credentials`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-black/[0.08] bg-white">
      <button
        type="button"
        disabled={isPublic || connected === true}
        onClick={() => !isPublic && setExpanded((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left disabled:cursor-default"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot}`} />
        <span className="flex-1 text-[13px] font-medium text-[#101828]">{label}</span>
        {connected === null ? (
          <Loader2 size={12} className="shrink-0 animate-spin text-[#98a2b3]" />
        ) : connected ? (
          <CheckCircle2 size={14} className="shrink-0 text-[#17b26a]" />
        ) : (
          <span className="shrink-0 text-[11px] font-semibold text-[#7c3aed]">
            {expanded ? "Cancel" : "Connect"}
          </span>
        )}
      </button>

      {expanded && !isPublic && def ? (
        <div className="border-t border-black/[0.06] px-3 pb-3 pt-2.5">
          <div className="space-y-2">
            {def.fields.map((field) => (
              <label key={field.key} className="block">
                <span className="mb-1 block text-[11px] font-medium text-[#475467]">{field.label}</span>
                <div className="flex items-center gap-1.5">
                  <input
                    type={field.sensitive && !revealed[field.key] ? "password" : "text"}
                    value={draft[field.key] || ""}
                    onChange={(e) => setDraft((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    placeholder={field.placeholder}
                    autoComplete="off"
                    className="min-w-0 flex-1 rounded-lg border border-black/[0.12] bg-[#f8fafc] px-2.5 py-1.5 text-[12px] text-[#101828] outline-none focus:border-[#94a3b8]"
                  />
                  {field.sensitive ? (
                    <button
                      type="button"
                      onClick={() => setRevealed((r) => ({ ...r, [field.key]: !r[field.key] }))}
                      className="shrink-0 text-[#98a2b3] hover:text-[#475467]"
                    >
                      {revealed[field.key] ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                  ) : null}
                </div>
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-[#7c3aed] px-3 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-[#6d28d9] disabled:opacity-55"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : null}
            Save & connect
          </button>
        </div>
      ) : null}
    </div>
  );
}

export { ConnectorRow };
