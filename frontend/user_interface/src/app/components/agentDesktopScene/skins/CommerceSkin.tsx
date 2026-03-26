import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, InfoCell, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** Stripe / Shopify / QuickBooks / Xero — transaction view with amounts. */
function CommerceSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} subtitle={state.summaryText} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <InfoCell label={descriptor.objectLabel} value={state.objectId || "pending"} palette={palette} />
        <InfoCell label="Amount" value={String(data["amount"] || data["total"] || data["value"] || "—")} palette={palette} />
        <InfoCell label="Status" value={state.statusLabel || "processing"} palette={palette} />
      </div>

      <ToolParamsPreview
        data={data}
        palette={palette}
        fields={[
          { key: "customer_id", label: "Customer" },
          { key: "currency", label: "Currency" },
          { key: "description", label: "Description" },
          { key: "line_items", label: "Line items" },
          { key: "due_date", label: "Due date" },
        ]}
      />

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { CommerceSkin };
