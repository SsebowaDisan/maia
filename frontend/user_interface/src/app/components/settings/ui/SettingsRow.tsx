import type { ReactNode } from "react";

type SettingsRowProps = {
  title: string;
  description?: string;
  right?: ReactNode;
  children?: ReactNode;
  noDivider?: boolean;
  className?: string;
};

export function SettingsRow({
  title,
  description,
  right,
  children,
  noDivider = false,
  className = "",
}: SettingsRowProps) {
  return (
    <div
      className={`px-5 py-4 sm:px-6 sm:py-5 ${noDivider ? "" : "border-b border-[#f2f2f4]"} ${className}`.trim()}
    >
      <div className="flex min-h-[56px] flex-wrap items-center justify-between gap-4">
        <div className="min-w-[220px] flex-1">
          <p className="text-[14px] font-semibold text-[#1d1d1f]">{title}</p>
          {description ? <p className="mt-1 text-[12px] text-[#6e6e73]">{description}</p> : null}
        </div>
        {right ? <div className="flex flex-wrap items-center justify-end gap-2">{right}</div> : null}
      </div>
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}
