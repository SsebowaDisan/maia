import { suiteAccentClass } from "./catalogModel";
import { ConnectorCatalogCard } from "./ConnectorCatalogCard";
import type { ConnectorSuiteFilter, ConnectorSuiteSection as ConnectorSuiteSectionRecord } from "./catalogModel";

type ConnectorSuiteSectionProps = {
  section: ConnectorSuiteSectionRecord;
  activeSuite: ConnectorSuiteFilter;
  onOpenConnector: (connectorId: string) => void;
};

export function ConnectorSuiteSection({
  section,
  activeSuite,
  onOpenConnector,
}: ConnectorSuiteSectionProps) {
  return (
    <article className="rounded-[20px] border border-black/[0.06] bg-white p-4">
      {activeSuite === "all" ? (
        <div className="mb-4 flex items-center gap-2.5 px-1">
          <span
            className={`inline-block h-2 w-2 shrink-0 rounded-full ${suiteAccentClass(
              section.key,
            )}`}
          />
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[#1d1d1f]">
            {section.label}
          </h2>
          <span className="text-[12px] text-[#86868b]">
            {section.connectors.length}
          </span>
          <span className="ml-2 text-[12px] text-[#c7c7cc]">
            {section.description}
          </span>
        </div>
      ) : (
        <div className="mb-4 px-1">
          <p className="text-[12px] text-[#86868b]">{section.description}</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {section.connectors.map((connector) => (
          <ConnectorCatalogCard
            key={connector.id}
            connector={connector}
            onOpen={onOpenConnector}
          />
        ))}
      </div>
    </article>
  );
}
