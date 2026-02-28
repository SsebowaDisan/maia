import { Activity } from "lucide-react";

type EventStyle = {
  label: string;
  icon: typeof Activity;
  accent: string;
};

type PreviewTab = "browser" | "document" | "email" | "system";

export type { EventStyle, PreviewTab };
