import { ConnectorBrandIcon } from "./ConnectorBrandIcon";
import type { ConnectorSubService } from "../../types/connectorSummary";

type ConnectorServiceListProps = {
  services: ConnectorSubService[];
  variant?: "compact" | "detail";
  title?: string;
};

function serviceStatusClass(status: ConnectorSubService["status"]): string {
  if (status === "Connected") {
    return "border-[#c7ead8] bg-[#edf9f2] text-[#166534]";
  }
  if (status === "Needs permission") {
    return "border-[#fbd38d] bg-[#fff7ed] text-[#9a3412]";
  }
  if (status === "Needs setup") {
    return "border-[#d0d5dd] bg-[#f8fafc] text-[#667085]";
  }
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#667085]";
}

export function ConnectorServiceList({
  services,
  variant = "compact",
  title = "Services",
}: ConnectorServiceListProps) {
  if (!services.length) {
    return null;
  }

  if (variant === "detail") {
    return (
      <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          {title}
        </p>
        <div className="mt-2 space-y-2">
          {services.map((service) => (
            <div
              key={service.id}
              className="flex items-start justify-between gap-3 rounded-xl border border-black/[0.06] bg-[#f8fafc] px-3 py-2"
            >
              <div className="flex min-w-0 items-start gap-2.5">
                <div className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[10px] border border-black/[0.06] bg-white">
                  <ConnectorBrandIcon
                    connectorId={service.id}
                    brandSlug={service.brandSlug}
                    label={service.label}
                    size={16}
                  />
                </div>
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-[#101828]">
                    {service.label}
                  </p>
                  <p className="text-[12px] text-[#667085]">
                    {service.description}
                  </p>
                  {service.requiredScopes?.length ? (
                    <p className="mt-1 text-[11px] text-[#98a2b3]">
                      Required permissions: {service.requiredScopes.join(", ")}
                    </p>
                  ) : null}
                </div>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-semibold ${serviceStatusClass(
                  service.status,
                )}`}
              >
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-current/70" />
                {service.status}
              </span>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <div className="rounded-xl border border-black/[0.04] bg-[#fafafa] p-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#86868b]">
        {title}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {services.map((service) => (
          <span
            key={service.id}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-medium ${serviceStatusClass(
              service.status,
            )}`}
            title={service.description}
          >
            <ConnectorBrandIcon
              connectorId={service.id}
              brandSlug={service.brandSlug}
              label={service.label}
              size={12}
            />
            {service.label}
          </span>
        ))}
      </div>
    </div>
  );
}
