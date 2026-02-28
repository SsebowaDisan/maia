type ResourceTab =
  | "indexCollections"
  | "llms"
  | "embeddings"
  | "rerankings"
  | "users";

type ViewTab = "view" | "add";
type UserTab = "userlist" | "createuser";

type ModelTab = "llms" | "embeddings" | "rerankings";

type ModelFormState = {
  name: string;
  vendor: string;
  specification: string;
  setAsDefault: boolean;
};

type TableColumn = {
  key: string;
  label: string;
};

type TableRow = Record<string, string | number | boolean>;

type ModelFormCopy = {
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

export type {
  ModelFormCopy,
  ModelFormState,
  ModelTab,
  ResourceTab,
  TableColumn,
  TableRow,
  UserTab,
  ViewTab,
};
