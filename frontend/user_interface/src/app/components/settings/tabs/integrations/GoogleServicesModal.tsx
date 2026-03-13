import type { GoogleServiceDefinition } from "./googleServices";

type GoogleServicesModalProps = {
  open: boolean;
  busy: boolean;
  modalConnectPending: boolean;
  draftServices: string[];
  draftScopesCount: number;
  serviceDefinitions: GoogleServiceDefinition[];
  onClose: () => void;
  onCancel: () => void;
  onContinue: () => Promise<void>;
  onToggleDraftService: (serviceId: string, checked: boolean) => void;
};

function GoogleServicesModal({
  open,
  busy,
  modalConnectPending,
  draftServices,
  draftScopesCount,
  serviceDefinitions,
  onClose,
  onCancel,
  onContinue,
  onToggleDraftService,
}: GoogleServicesModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/35 px-4 backdrop-blur-[10px]"
      role="dialog"
      aria-modal="true"
      aria-label="Choose Google services"
      onClick={() => {
        if (!modalConnectPending) {
          onClose();
        }
      }}
    >
      <div
        className="w-full max-w-[560px] rounded-2xl border border-[#d2d2d7] bg-white p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="text-[20px] font-semibold text-[#1d1d1f]">Choose services</p>
        <p className="mt-1 text-[13px] text-[#6e6e73]">Choose what Maia can access in your Google account.</p>
        <div className="mt-4 space-y-2">
          {serviceDefinitions.map((service) => {
            const checked = draftServices.includes(service.id);
            return (
              <label
                key={`modal-${service.id}`}
                className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#ececf0] bg-[#fafafc] px-3 py-2"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => onToggleDraftService(service.id, event.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-[#d2d2d7]"
                />
                <span>
                  <span className="block text-[13px] font-semibold text-[#1d1d1f]">{service.label}</span>
                  <span className="block text-[12px] text-[#6e6e73]">{service.description}</span>
                </span>
              </label>
            );
          })}
        </div>
        <p className="mt-3 text-[11px] text-[#6e6e73]">Scopes requested: {draftScopesCount}</p>
        {modalConnectPending ? (
          <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-1 text-[11px] text-[#4a4a4f]">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#b9b9bf] border-t-[#1d1d1f]" />
            Opening Google sign-in...
          </div>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            disabled={modalConnectPending}
            onClick={onCancel}
            className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || modalConnectPending || draftServices.length === 0}
            onClick={() => void onContinue()}
            className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white transition-all duration-150 hover:bg-[#2f2f34] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {modalConnectPending ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/45 border-t-white" />
                Opening...
              </span>
            ) : (
              "Continue to Google"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export { GoogleServicesModal };
