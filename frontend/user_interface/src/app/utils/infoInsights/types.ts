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

type SourceGraphNode = {
  id: string;
  kind: "claim" | "source";
  label: string;
  status?: ClaimStatus;
  score?: number;
  evidenceCount?: number;
};

type SourceGraphEdge = {
  id: string;
  claimId: string;
  sourceId: string;
  weight: number;
  evidenceIds: string[];
};

type SourceGraph = {
  claimNodes: SourceGraphNode[];
  sourceNodes: SourceGraphNode[];
  edges: SourceGraphEdge[];
  orphanClaimIds: string[];
};

type ContradictionSeverity = "high" | "medium" | "low";

type ContradictionFinding = {
  id: string;
  severity: ContradictionSeverity;
  summary: string;
  detail: string;
  confidence: number;
  claimId?: string;
  evidenceId?: string;
  source?: string;
  relatedClaimId?: string;
};

type NumericFact = {
  value: number;
  unit: string;
  raw: string;
};

export type {
  ClaimInsight,
  ClaimStatus,
  ContradictionFinding,
  ContradictionSeverity,
  EvidenceCard,
  NumericFact,
  SourceGraph,
  SourceGraphEdge,
  SourceGraphNode,
};
