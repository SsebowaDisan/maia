type RoutePlaceholderPageProps = {
  title: string;
  description: string;
  path: string;
};

export function RoutePlaceholderPage({ title, description, path }: RoutePlaceholderPageProps) {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#eef1f5] p-6">
      <div className="w-full max-w-[720px] rounded-[28px] border border-black/[0.08] bg-white px-8 py-9 shadow-[0_28px_70px_rgba(15,23,42,0.14)]">
        <p className="text-[12px] font-semibold uppercase tracking-[0.2em] text-[#667085]">Route placeholder</p>
        <h1 className="mt-2 text-[34px] font-semibold leading-[1.15] tracking-[-0.02em] text-[#101828]">{title}</h1>
        <p className="mt-3 text-[16px] leading-[1.6] text-[#475467]">{description}</p>
        <div className="mt-7 rounded-2xl border border-black/[0.08] bg-[#f8fafc] px-4 py-3">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Path</p>
          <p className="mt-1 text-[14px] font-medium text-[#111827]">{path}</p>
        </div>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <a
            href="/"
            className="inline-flex items-center rounded-full bg-[#111827] px-5 py-2.5 text-[14px] font-medium text-white transition hover:bg-[#1f2937]"
          >
            Back to Chat
          </a>
          <a
            href="/connectors"
            className="inline-flex items-center rounded-full border border-black/[0.14] bg-white px-5 py-2.5 text-[14px] font-medium text-[#111827] transition hover:border-black/[0.24]"
          >
            Open Connectors
          </a>
        </div>
      </div>
    </div>
  );
}
