export { buildClaimInsights, extractClaims, supportRate } from "./claims";
export { detectContradictions } from "./contradictions";
export { parseEvidence } from "./evidence";
export { buildSourceGraph } from "./graph";
export type {
  ClaimInsight,
  ClaimStatus,
  ContradictionFinding,
  ContradictionSeverity,
  EvidenceCard,
  SourceGraph,
  SourceGraphEdge,
  SourceGraphNode,
} from "./types";
