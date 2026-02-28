import type {
  ModelFormCopy,
  ResourceTab,
  TableColumn,
  TableRow,
  UserTab,
  ViewTab,
} from "./types";

const resourceTabs: Array<{ id: ResourceTab; label: string }> = [
  { id: "indexCollections", label: "Index Collections" },
  { id: "llms", label: "LLMs" },
  { id: "embeddings", label: "Embeddings" },
  { id: "rerankings", label: "Rerankings" },
  { id: "users", label: "Users" },
];

const viewTabs: Array<{ id: ViewTab; label: string }> = [
  { id: "view", label: "View" },
  { id: "add", label: "Add" },
];

const userTabs: Array<{ id: UserTab; label: string }> = [
  { id: "userlist", label: "User list" },
  { id: "createuser", label: "Create user" },
];

const vendorOptions = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google" },
  { value: "groq", label: "Groq" },
  { value: "cohere", label: "Cohere" },
  { value: "mistral", label: "Mistral" },
];

const tableColumns: Record<
  "indexCollections" | "llms" | "embeddings" | "rerankings" | "users",
  TableColumn[]
> = {
  indexCollections: [
    { key: "id", label: "id" },
    { key: "name", label: "name" },
    { key: "indexType", label: "index_type" },
  ],
  llms: [
    { key: "name", label: "name" },
    { key: "vendor", label: "vendor" },
    { key: "default", label: "default" },
  ],
  embeddings: [
    { key: "name", label: "name" },
    { key: "vendor", label: "vendor" },
    { key: "default", label: "default" },
  ],
  rerankings: [
    { key: "name", label: "name" },
    { key: "vendor", label: "vendor" },
    { key: "default", label: "default" },
  ],
  users: [
    { key: "username", label: "username" },
    { key: "admin", label: "admin" },
  ],
};

const tableRows: Record<
  "indexCollections" | "llms" | "embeddings" | "rerankings" | "users",
  TableRow[]
> = {
  indexCollections: [
    { id: "1", name: "File Collection", indexType: "FileIndex" },
    { id: "2", name: "GraphRAG Collection", indexType: "GraphRAGIndex" },
    { id: "3", name: "LightRAG Collection", indexType: "LightRAGIndex" },
  ],
  llms: [
    { name: "openai", vendor: "ChatOpenAI", default: "false" },
    { name: "claude", vendor: "LCAnthropicChat", default: "false" },
    { name: "google", vendor: "LCGeminiChat", default: "true" },
    { name: "groq", vendor: "ChatOpenAI", default: "false" },
    { name: "cohere", vendor: "LCCohereChat", default: "false" },
    { name: "mistral", vendor: "ChatOpenAI", default: "false" },
  ],
  embeddings: [
    { name: "openai", vendor: "OpenAIEmbeddings", default: "false" },
    { name: "cohere", vendor: "LCCohereEmbeddings", default: "false" },
    { name: "google", vendor: "LCGoogleEmbeddings", default: "true" },
    { name: "mistral", vendor: "LCMistralEmbeddings", default: "false" },
  ],
  rerankings: [{ name: "cohere", vendor: "CohereReranking", default: "true" }],
  users: [{ username: "admin", admin: "true" }],
};

const modelFormCopyByTab: Record<"llms" | "embeddings" | "rerankings", ModelFormCopy> = {
  llms: {
    title: "LLM",
    nameLabel: "LLM name",
    nameHelp: "Must be unique. The name will be used to identify the LLM.",
    vendorLabel: "LLM vendors",
    vendorHelp: "Choose the vendor for the LLM. Each vendor has different specification.",
    specificationLabel: "Specification",
    specificationHelp: "Specification of the LLM in YAML format",
    defaultHelp:
      "Set this LLM as default. This default LLM will be used by default across the application.",
    buttonLabel: "Add LLM",
    rightPanelHelp: "Select an LLM to view the spec description.",
  },
  embeddings: {
    title: "Embedding",
    nameLabel: "Embedding name",
    nameHelp: "Must be unique. The name will be used to identify the embedding.",
    vendorLabel: "Embedding vendors",
    vendorHelp:
      "Choose the vendor for the embedding. Each vendor has different specification.",
    specificationLabel: "Specification",
    specificationHelp: "Specification of the embedding in YAML format",
    defaultHelp:
      "Set this embedding as default. This default embedding will be used by default across the application.",
    buttonLabel: "Add Embedding",
    rightPanelHelp: "Select an embedding to view the spec description.",
  },
  rerankings: {
    title: "Reranking",
    nameLabel: "Reranking name",
    nameHelp: "Must be unique. The name will be used to identify the reranking.",
    vendorLabel: "Reranking vendors",
    vendorHelp:
      "Choose the vendor for the reranking. Each vendor has different specification.",
    specificationLabel: "Specification",
    specificationHelp: "Specification of the reranking in YAML format",
    defaultHelp:
      "Set this reranking as default. This default reranking will be used by default across the application.",
    buttonLabel: "Add Reranking",
    rightPanelHelp: "Select a reranking to view the spec description.",
  },
};

export {
  modelFormCopyByTab,
  resourceTabs,
  tableColumns,
  tableRows,
  userTabs,
  vendorOptions,
  viewTabs,
};
