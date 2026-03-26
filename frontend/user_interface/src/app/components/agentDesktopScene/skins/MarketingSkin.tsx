import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, InfoCell, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** Mailchimp / Webflow — campaign view with audience and status. */
function MarketingSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} subtitle={state.summaryText} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <InfoCell label="Campaign" value={String(data["campaign_name"] || data["name"] || state.objectType || "Campaign")} palette={palette} />
        <InfoCell label="Audience" value={String(data["list_id"] || data["audience"] || data["collection_id"] || "All subscribers")} palette={palette} />
        <InfoCell label="Status" value={state.statusLabel || "draft"} palette={palette} />
      </div>

      <ToolParamsPreview
        data={data}
        palette={palette}
        fields={[
          { key: "subject", label: "Subject line" },
          { key: "body", label: "Content preview" },
          { key: "send_time", label: "Send time" },
          { key: "fields", label: "CMS fields" },
        ]}
      />

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { MarketingSkin };
