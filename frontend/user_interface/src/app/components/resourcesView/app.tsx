import { useState } from "react";
import { AddSection } from "./AddSection";
import { resourceTabs, userTabs, viewTabs } from "./constants";
import { TabStrip } from "./TabStrip";
import type { ModelFormState, ResourceTab, UserTab, ViewTab } from "./types";
import { ViewSection } from "./ViewSection";

const emptyModelFormState: ModelFormState = {
  name: "",
  vendor: "",
  specification: "",
  setAsDefault: false,
};

function ResourcesView() {
  const [activeResourceTab, setActiveResourceTab] =
    useState<ResourceTab>("indexCollections");
  const [viewTab, setViewTab] = useState<ViewTab>("view");
  const [userTab, setUserTab] = useState<UserTab>("userlist");
  const [llmForm, setLlmForm] = useState<ModelFormState>(emptyModelFormState);
  const [embeddingForm, setEmbeddingForm] =
    useState<ModelFormState>(emptyModelFormState);
  const [rerankingForm, setRerankingForm] =
    useState<ModelFormState>(emptyModelFormState);

  return (
    <div className="flex-1 flex flex-col bg-white overflow-hidden">
      <div className="border-b border-[#e5e5e5]">
        <div className="px-8 pt-6 pb-3">
          <TabStrip
            tabs={resourceTabs}
            activeTab={activeResourceTab}
            onChange={setActiveResourceTab}
            className="gap-8 border-b-0"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="p-8">
          {activeResourceTab !== "users" ? (
            <TabStrip
              tabs={viewTabs}
              activeTab={viewTab}
              onChange={setViewTab}
              className="mb-8"
            />
          ) : (
            <TabStrip
              tabs={userTabs}
              activeTab={userTab}
              onChange={setUserTab}
              className="mb-8"
            />
          )}

          {viewTab === "view" || activeResourceTab === "users" ? (
            <ViewSection activeResourceTab={activeResourceTab} userTab={userTab} />
          ) : (
            <AddSection
              activeResourceTab={activeResourceTab}
              llmForm={llmForm}
              embeddingForm={embeddingForm}
              rerankingForm={rerankingForm}
              onLlmFormChange={setLlmForm}
              onEmbeddingFormChange={setEmbeddingForm}
              onRerankingFormChange={setRerankingForm}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export { ResourcesView };
