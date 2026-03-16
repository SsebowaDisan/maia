type GenericJsonWidgetProps = {
  title?: string;
  [key: string]: unknown;
};

function GenericJsonWidget({ title = "Widget data", ...props }: GenericJsonWidgetProps) {
  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-3 shadow-[0_10px_24px_rgba(15,23,42,0.05)]">
      <p className="text-[12px] font-semibold text-[#344054]">{title}</p>
      <pre className="mt-2 overflow-x-auto rounded-xl border border-black/[0.06] bg-[#f8fafc] p-3 text-[11px] leading-5 text-[#475467]">
        {JSON.stringify(props, null, 2)}
      </pre>
    </div>
  );
}

export { GenericJsonWidget };
