import { tableColumns, tableRows } from "./constants";
import { ResourceTable } from "./ResourceTable";
import type { ResourceTab, UserTab } from "./types";

type ViewSectionProps = {
  activeResourceTab: ResourceTab;
  userTab: UserTab;
};

function ViewSection({ activeResourceTab, userTab }: ViewSectionProps) {
  if (activeResourceTab === "users") {
    if (userTab === "createuser") {
      return <div className="py-12 text-center text-[13px] text-[#86868b]">Create user form</div>;
    }
    return <ResourceTable columns={tableColumns.users} rows={tableRows.users} />;
  }

  if (activeResourceTab === "indexCollections") {
    return (
      <ResourceTable
        columns={tableColumns.indexCollections}
        rows={tableRows.indexCollections}
      />
    );
  }

  if (activeResourceTab === "llms") {
    return <ResourceTable columns={tableColumns.llms} rows={tableRows.llms} />;
  }

  if (activeResourceTab === "embeddings") {
    return (
      <ResourceTable
        columns={tableColumns.embeddings}
        rows={tableRows.embeddings}
      />
    );
  }

  if (activeResourceTab === "rerankings") {
    return (
      <ResourceTable
        columns={tableColumns.rerankings}
        rows={tableRows.rerankings}
      />
    );
  }

  return null;
}

export { ViewSection };
