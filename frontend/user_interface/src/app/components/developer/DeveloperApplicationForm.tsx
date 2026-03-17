import { useState } from "react";
import { FileText, Send } from "lucide-react";
import { toast } from "sonner";

import { applyForDeveloper } from "../../../api/client";

type DeveloperApplicationFormProps = {
  onSuccess: () => void;
};

export function DeveloperApplicationForm({ onSuccess }: DeveloperApplicationFormProps) {
  const [motivation, setMotivation] = useState("");
  const [intendedTypes, setIntendedTypes] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = motivation.trim().length >= 20 && agreed && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const result = await applyForDeveloper({
        motivation: motivation.trim(),
        intended_agent_types: intendedTypes.trim(),
        agreed_to_guidelines: true,
      });
      toast.success(result.message);
      onSuccess();
    } catch (error) {
      toast.error(String((error as Error).message || "Failed to submit application."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[520px] py-10">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f5f3ff]">
          <FileText className="h-5 w-5 text-[#7c3aed]" />
        </div>
        <div>
          <h2 className="text-[15px] font-semibold text-[#1d1d1f]">
            Become a Developer
          </h2>
          <p className="text-[12px] text-[#86868b]">
            Apply to publish agents on the Maia marketplace
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-[12px] font-medium text-[#86868b]">
            Why do you want to publish agents? *
          </span>
          <textarea
            value={motivation}
            onChange={(e) => setMotivation(e.target.value)}
            placeholder="Describe your use case, expertise, and what kind of agents you plan to build (min 20 characters)"
            rows={4}
            className="w-full rounded-xl border border-black/[0.08] bg-white px-3 py-2.5 text-[13px] text-[#1d1d1f] outline-none transition placeholder:text-[#c7c7cc] focus:border-[#7c3aed]/40 focus:ring-2 focus:ring-[#7c3aed]/10"
          />
          <span className="mt-0.5 block text-right text-[11px] text-[#c7c7cc]">
            {motivation.length} characters
          </span>
        </label>

        <label className="block">
          <span className="mb-1.5 block text-[12px] font-medium text-[#86868b]">
            What types of agents do you plan to build?
          </span>
          <input
            value={intendedTypes}
            onChange={(e) => setIntendedTypes(e.target.value)}
            placeholder="e.g. CRM automation, research agents, data pipelines"
            className="w-full rounded-xl border border-black/[0.08] bg-white px-3 py-2.5 text-[13px] text-[#1d1d1f] outline-none transition placeholder:text-[#c7c7cc] focus:border-[#7c3aed]/40 focus:ring-2 focus:ring-[#7c3aed]/10"
          />
        </label>

        <label className="flex items-start gap-2.5 pt-1">
          <input
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-black/[0.15] text-[#7c3aed] accent-[#7c3aed]"
          />
          <span className="text-[12px] leading-relaxed text-[#6e6e73]">
            I agree to the{" "}
            <span className="font-medium text-[#7c3aed]">Developer Guidelines</span>
            {" "}and will follow marketplace policies for agent safety, quality,
            and responsible AI usage.
          </span>
        </label>
      </div>

      <button
        type="button"
        disabled={!canSubmit}
        onClick={handleSubmit}
        className="mt-6 inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-[#7c3aed] text-[13px] font-semibold text-white shadow-[0_2px_8px_-2px_rgba(124,58,237,0.4)] transition hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Send className="h-3.5 w-3.5" />
        {submitting ? "Submitting…" : "Submit Application"}
      </button>
    </div>
  );
}
