import type { ReactNode } from "react";

type SettingsSectionProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function SettingsSection({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: SettingsSectionProps) {
  return (
    <section className={`space-y-4 ${className}`.trim()}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[20px] font-semibold text-[#1d1d1f]">{title}</h2>
          {subtitle ? <p className="mt-1 text-[13px] text-[#6e6e73]">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="rounded-2xl border border-[#ececf0] bg-white">{children}</div>
    </section>
  );
}
