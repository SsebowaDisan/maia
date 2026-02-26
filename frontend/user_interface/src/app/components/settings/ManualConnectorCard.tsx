import type { ConnectorCredentialRecord } from "../../../api/client";
import type { ConnectorDefinition } from "./connectorDefinitions";

type ConnectorHealth = {
  ok: boolean;
  message: string;
};

type ManualConnectorCardProps = {
  connector: ConnectorDefinition;
  health?: ConnectorHealth;
  stored?: ConnectorCredentialRecord;
  currentDraft: Record<string, string>;
  busy: boolean;
  onDraftChange: (fieldKey: string, value: string) => void;
  onSave: () => void;
  onClear: () => void;
};

function statusChip(ok: boolean | null) {
  if (ok === null) {
    return "border-[#d2d2d7] bg-[#f5f5f7] text-[#6e6e73]";
  }
  return ok
    ? "border-[#5f8a68] bg-[#f0f7f1] text-[#2d5937]"
    : "border-[#d2d2d7] bg-[#f5f5f7] text-[#6e6e73]";
}

export function ManualConnectorCard({
  connector,
  health,
  stored,
  currentDraft,
  busy,
  onDraftChange,
  onSave,
  onClear,
}: ManualConnectorCardProps) {
  const storedKeys = Object.entries(stored?.values || {})
    .filter((entry) => String(entry[1] || "").length > 0)
    .map((entry) => entry[0]);

  return (
    <section className="rounded-2xl border border-[#ececf0] bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-[16px] font-semibold text-[#1d1d1f]">{connector.label}</h3>
          <p className="mt-1 text-[13px] text-[#6e6e73]">{connector.description}</p>
        </div>
        <div
          className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${statusChip(health ? health.ok : null)}`}
        >
          {health ? (health.ok ? "Configured" : "Missing config") : "Unknown"}
        </div>
      </div>

      {health?.message ? <p className="mt-3 text-[12px] text-[#6e6e73]">{health.message}</p> : null}

      <div className="mt-5 grid grid-cols-1 lg:grid-cols-2 gap-3">
        {connector.fields.map((field) => (
          <label key={field.key} className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[#3a3a3c]">{field.label}</span>
            <input
              type={field.sensitive ? "password" : "text"}
              value={currentDraft[field.key] || ""}
              onChange={(event) => onDraftChange(field.key, event.target.value)}
              className="w-full rounded-xl border border-[#d2d2d7] bg-[#fafafa] px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
              placeholder={field.placeholder}
              autoComplete="off"
            />
          </label>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-60"
        >
          Save credentials
        </button>
        <button
          onClick={onClear}
          disabled={busy || !stored}
          className="rounded-xl border border-[#d2d2d7] bg-white px-4 py-2 text-[13px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
        >
          Clear
        </button>
        {stored?.date_updated ? (
          <span className="text-[12px] text-[#6e6e73]">
            Updated {new Date(stored.date_updated).toLocaleString()}
          </span>
        ) : null}
      </div>

      {storedKeys.length > 0 ? (
        <p className="mt-3 text-[12px] text-[#6e6e73]">Stored keys: {storedKeys.join(", ")}</p>
      ) : null}
    </section>
  );
}
