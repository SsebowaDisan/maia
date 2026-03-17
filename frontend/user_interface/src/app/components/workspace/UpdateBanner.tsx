type UpdateBannerProps = {
  totalUpdates: number;
  onOpenUpdates: () => void;
  onDismiss: () => void;
};

export function UpdateBanner({ totalUpdates, onOpenUpdates, onDismiss }: UpdateBannerProps) {
  if (totalUpdates <= 0) {
    return null;
  }
  return (
    <div className="rounded-2xl border border-[#c7d7fe] bg-[#eef4ff] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-[#1d3f8f]">
          {totalUpdates} of your agents have updates available.
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onOpenUpdates}
            className="rounded-full bg-[#7c3aed] px-3 py-1.5 text-[12px] font-semibold text-white"
          >
            Review updates
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-full border border-[#c7d2fe] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1e3a8a]"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

