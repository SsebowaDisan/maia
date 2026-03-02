type EvidenceCard = {
  id: string;
  title: string;
  source: string;
  page?: string;
  fileId?: string;
  extract: string;
  imageSrc?: string;
};

type ClaimStatus = "supported" | "weak" | "missing";

type ClaimInsight = {
  id: string;
  text: string;
  status: ClaimStatus;
  matchedEvidenceIds: string[];
  score: number;
};

export type {
  ClaimInsight,
  ClaimStatus,
  EvidenceCard,
};
