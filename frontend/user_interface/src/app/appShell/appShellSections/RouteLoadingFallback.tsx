export function RouteLoadingFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#f6f6f7] p-6">
      <div className="w-full max-w-[720px] rounded-[28px] border border-black/[0.08] bg-white px-8 py-9 shadow-[0_28px_70px_rgba(15,23,42,0.14)]">
        <p className="text-[12px] font-semibold uppercase tracking-[0.2em] text-[#667085]">Loading</p>
        <h1 className="mt-2 text-[34px] font-semibold leading-[1.15] tracking-[-0.02em] text-[#101828]">
          Preparing workspace
        </h1>
        <p className="mt-3 text-[16px] leading-[1.6] text-[#475467]">
          Maia is loading the next surface and keeping the current session state intact.
        </p>
        <div className="mt-7 h-2 w-full overflow-hidden rounded-full bg-[#e5e7eb]">
          <div className="h-full w-1/3 rounded-full bg-[#111827]" />
        </div>
      </div>
    </div>
  );
}
