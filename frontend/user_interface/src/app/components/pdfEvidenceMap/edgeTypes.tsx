import { BaseEdge, type EdgeProps } from "@xyflow/react";

function trimEdge(
  cx: number,
  cy: number,
  ox: number,
  oy: number,
  hw: number,
  hh: number,
): { x: number; y: number } {
  const dx = ox - cx;
  const dy = oy - cy;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) {
    return { x: cx, y: cy };
  }
  const abscos = Math.abs(dx / len);
  const abssin = Math.abs(dy / len);
  const d = abscos > 0 && abssin > 0 ? Math.min(hw / abscos, hh / abssin) : abscos > 0 ? hw : hh;
  return { x: cx + (dx / len) * d, y: cy + (dy / len) * d };
}

function CurvedMindEdge({ id, data, style }: EdgeProps) {
  const edge = (data ?? {}) as { sx?: number; sy?: number; tx?: number; ty?: number };
  const srcX = Number(edge.sx ?? 0);
  const srcY = Number(edge.sy ?? 0);
  const tgtX = Number(edge.tx ?? 0);
  const tgtY = Number(edge.ty ?? 0);
  const isRoot = srcX * srcX + srcY * srcY < 25;
  const start = trimEdge(srcX, srcY, tgtX, tgtY, isRoot ? 92 : 76, isRoot ? 22 : 28);
  const end = trimEdge(tgtX, tgtY, srcX, srcY, 76, 28);
  const mx = (start.x + end.x) / 2;
  const my = (start.y + end.y) / 2;
  const midLen = Math.sqrt(mx * mx + my * my) || 1;
  const edgeLen = Math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2);
  const bow = Math.min(32, edgeLen * 0.12);
  const cpx = mx - (mx / midLen) * bow;
  const cpy = my - (my / midLen) * bow;
  return (
    <BaseEdge
      id={id}
      path={`M ${start.x} ${start.y} Q ${cpx} ${cpy} ${end.x} ${end.y}`}
      style={style}
    />
  );
}

const edgeTypes = { mindCurve: CurvedMindEdge };

export { edgeTypes };
