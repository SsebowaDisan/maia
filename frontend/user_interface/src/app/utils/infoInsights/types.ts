type HighlightBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type EvidenceUnit = {
  text: string;
  highlightBoxes: HighlightBox[];
  charStart?: number;
  charEnd?: number;
};

type EvidenceCard = {
  id: string;
  title: string;
  source: string;
  sourceType?: string;
  sourceUrl?: string;
  page?: string;
  fileId?: string;
  chunkId?: string;
  extract: string;
  imageSrc?: string;
  highlightBoxes?: HighlightBox[];
  evidenceUnits?: EvidenceUnit[];
  confidence?: number;
  collectedBy?: string;
  graphNodeIds?: string[];
  sceneRefs?: string[];
  eventRefs?: string[];
  strengthScore?: number;
  strengthTier?: number;
  matchQuality?: string;
  unitId?: string;
  selector?: string;
  charStart?: number;
  charEnd?: number;
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
  HighlightBox,
  EvidenceUnit,
};
