import { modelFormCopyByTab, vendorOptions } from "./constants";
import type { ModelFormState, ResourceTab } from "./types";

type ModelFormCardProps = {
  form: ModelFormState;
  copy: {
    title: string;
    nameLabel: string;
    nameHelp: string;
    vendorLabel: string;
    vendorHelp: string;
    specificationLabel: string;
    specificationHelp: string;
    defaultHelp: string;
    buttonLabel: string;
    rightPanelHelp: string;
  };
  onChange: (next: ModelFormState) => void;
};

function ModelFormCard({ form, copy, onChange }: ModelFormCardProps) {
  return (
    <div className="flex gap-6">
      <div className="w-[400px]">
        <div className="mb-6">
          <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
            {copy.nameLabel}
          </label>
          <p className="text-[11px] text-[#86868b] mb-3">{copy.nameHelp}</p>
          <input
            type="text"
            value={form.name}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
            className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
          />
        </div>

        <div className="mb-6">
          <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
            {copy.vendorLabel}
          </label>
          <p className="text-[11px] text-[#86868b] mb-3">{copy.vendorHelp}</p>
          <select
            value={form.vendor}
            onChange={(event) => onChange({ ...form, vendor: event.target.value })}
            className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
          >
            <option value="">Select vendor</option>
            {vendorOptions.map((vendor) => (
              <option key={vendor.value} value={vendor.value}>
                {vendor.label}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-6">
          <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
            {copy.specificationLabel}
          </label>
          <p className="text-[11px] text-[#86868b] mb-3">{copy.specificationHelp}</p>
          <textarea
            value={form.specification}
            onChange={(event) => onChange({ ...form, specification: event.target.value })}
            className="w-full px-3 py-3 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[12px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b] resize-none min-h-[120px] font-mono"
          />
        </div>

        <div className="mb-6">
          <p className="text-[11px] text-[#86868b] mb-2">{copy.defaultHelp}</p>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.setAsDefault}
              onChange={(event) =>
                onChange({ ...form, setAsDefault: event.target.checked })
              }
              className="w-4 h-4 rounded border-[#d2d2d7] text-[#1d1d1f] focus:ring-0 focus:ring-offset-0"
            />
            <span className="text-[13px] text-[#1d1d1f]">Set default</span>
          </label>
        </div>

        <button className="w-full px-4 py-3 bg-[#1d1d1f] hover:bg-[#424245] text-white rounded-lg text-[13px] font-medium transition-all">
          {copy.buttonLabel}
        </button>
      </div>

      <div className="flex-1 bg-[#fafafa] rounded-lg p-6">
        <h3 className="text-[15px] text-[#1d1d1f] font-medium mb-4">Spec description</h3>
        <p className="text-[13px] text-[#86868b]">{copy.rightPanelHelp}</p>
      </div>
    </div>
  );
}

type AddSectionProps = {
  activeResourceTab: ResourceTab;
  llmForm: ModelFormState;
  embeddingForm: ModelFormState;
  rerankingForm: ModelFormState;
  onLlmFormChange: (next: ModelFormState) => void;
  onEmbeddingFormChange: (next: ModelFormState) => void;
  onRerankingFormChange: (next: ModelFormState) => void;
};

function AddSection({
  activeResourceTab,
  llmForm,
  embeddingForm,
  rerankingForm,
  onLlmFormChange,
  onEmbeddingFormChange,
  onRerankingFormChange,
}: AddSectionProps) {
  if (activeResourceTab === "llms") {
    return (
      <ModelFormCard
        form={llmForm}
        copy={modelFormCopyByTab.llms}
        onChange={onLlmFormChange}
      />
    );
  }
  if (activeResourceTab === "embeddings") {
    return (
      <ModelFormCard
        form={embeddingForm}
        copy={modelFormCopyByTab.embeddings}
        onChange={onEmbeddingFormChange}
      />
    );
  }
  if (activeResourceTab === "rerankings") {
    return (
      <ModelFormCard
        form={rerankingForm}
        copy={modelFormCopyByTab.rerankings}
        onChange={onRerankingFormChange}
      />
    );
  }

  return (
    <div className="py-12 text-center text-[13px] text-[#86868b]">
      Add new {activeResourceTab} form
    </div>
  );
}

export { AddSection };
