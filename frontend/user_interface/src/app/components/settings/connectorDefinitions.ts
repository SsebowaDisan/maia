export type ConnectorField = {
  key: string;
  label: string;
  placeholder: string;
  sensitive?: boolean;
};

export type ConnectorDefinition = {
  id: string;
  label: string;
  description: string;
  fields: ConnectorField[];
};

export const MANUAL_CONNECTOR_DEFINITIONS: ConnectorDefinition[] = [
  {
    id: "slack",
    label: "Slack",
    description: "Post company updates and report digests to channels.",
    fields: [
      {
        key: "SLACK_BOT_TOKEN",
        label: "Bot token",
        placeholder: "xoxb-...",
        sensitive: true,
      },
    ],
  },
  {
    id: "google_ads",
    label: "Google Ads",
    description: "Read campaign metrics for KPI analysis and optimization.",
    fields: [
      {
        key: "GOOGLE_ADS_DEVELOPER_TOKEN",
        label: "Developer token",
        placeholder: "Google Ads developer token",
        sensitive: true,
      },
      {
        key: "GOOGLE_ADS_CUSTOMER_ID",
        label: "Customer ID",
        placeholder: "1234567890",
      },
      {
        key: "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        label: "Login customer ID",
        placeholder: "Optional manager account ID",
      },
    ],
  },
  {
    id: "bing_search",
    label: "Bing Web Search (Legacy)",
    description: "Optional fallback search provider if Brave is unavailable.",
    fields: [
      {
        key: "AZURE_BING_API_KEY",
        label: "Azure API key",
        placeholder: "Bing Web Search key",
        sensitive: true,
      },
      {
        key: "BING_SEARCH_ENDPOINT",
        label: "Endpoint",
        placeholder: "https://api.bing.microsoft.com/v7.0/search",
      },
    ],
  },
  {
    id: "email_validation",
    label: "Email Validation",
    description: "Validate outreach emails before send to reduce bounces.",
    fields: [
      {
        key: "EMAIL_VALIDATION_PROVIDER",
        label: "Provider",
        placeholder: "abstractapi or zerobounce",
      },
      {
        key: "EMAIL_VALIDATION_API_KEY",
        label: "API key",
        placeholder: "Email verification provider key",
        sensitive: true,
      },
    ],
  },
  {
    id: "m365",
    label: "Microsoft 365",
    description: "Use OneDrive and Excel via Microsoft Graph.",
    fields: [
      {
        key: "M365_ACCESS_TOKEN",
        label: "Access token",
        placeholder: "Bearer token",
        sensitive: true,
      },
    ],
  },
  {
    id: "invoice",
    label: "Invoice Providers",
    description: "Send invoices through QuickBooks or Xero.",
    fields: [
      {
        key: "QUICKBOOKS_ACCESS_TOKEN",
        label: "QuickBooks access token",
        placeholder: "Bearer token",
        sensitive: true,
      },
      {
        key: "QUICKBOOKS_REALM_ID",
        label: "QuickBooks realm ID",
        placeholder: "Company realm ID",
      },
      {
        key: "XERO_ACCESS_TOKEN",
        label: "Xero access token",
        placeholder: "Bearer token",
        sensitive: true,
      },
      {
        key: "XERO_TENANT_ID",
        label: "Xero tenant ID",
        placeholder: "Tenant ID",
      },
    ],
  },
];
