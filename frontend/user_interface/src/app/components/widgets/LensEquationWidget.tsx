import { useState } from "react";

type LensWidgetProps = {
  focalLength?: number;
  objectDistance?: number;
  showRays?: boolean;
  units?: string;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatDistance(value: number | null, units: string): string {
  if (value === null || !Number.isFinite(value)) {
    return "∞";
  }
  return `${value.toFixed(1)} ${units}`;
}

function LensEquationWidget({
  focalLength = 10,
  objectDistance = 30,
  showRays = true,
  units = "cm",
}: LensWidgetProps) {
  const safeFocalLength = clamp(Number(focalLength) || 10, 2, 40);
  const safeObjectDistance = clamp(Number(objectDistance) || 30, 2, 80);
  const [focal, setFocal] = useState(safeFocalLength);
  const [object, setObject] = useState(safeObjectDistance);
  const denominator = (1 / focal) - (1 / object);
  const atInfinity = Math.abs(object - focal) < 0.0001 || Math.abs(denominator) < 0.0001;
  const imageDistance = atInfinity ? null : 1 / denominator;
  const imageKind = atInfinity ? "At infinity" : object > focal ? "Real" : "Virtual";
  const magnification = imageDistance === null ? null : -imageDistance / object;

  const axisY = 120;
  const lensX = 250;
  const objectX = lensX - clamp((object / 80) * 160, 36, 185);
  const objectHeight = 74;
  const imageHeight =
    magnification === null ? 0 : clamp(Math.abs(magnification) * objectHeight, 20, 132);
  const imageX =
    imageDistance === null
      ? lensX + 190
      : imageDistance >= 0
        ? lensX + clamp((Math.abs(imageDistance) / 80) * 200, 30, 210)
        : lensX - clamp((Math.abs(imageDistance) / 80) * 170, 30, 210);
  const imageTopY =
    magnification === null
      ? axisY
      : magnification >= 0
        ? axisY - imageHeight
        : axisY + imageHeight;
  const imageBottomY = axisY;
  const principalFocusLeft = lensX - 68;
  const principalFocusRight = lensX + 68;
  const objectTipX = objectX;
  const objectTipY = axisY - objectHeight;
  const imageTipY = magnification === null ? axisY : imageTopY;

  return (
    <div className="overflow-hidden rounded-[28px] border border-black/[0.08] bg-[linear-gradient(180deg,#ffffff_0%,#f7f8fb_100%)] shadow-[0_20px_50px_rgba(15,23,42,0.08)]">
      <div className="border-b border-black/[0.06] px-5 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-full bg-[#e8eefc] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#3151a6]">
            Optics
          </div>
          <p className="text-[15px] font-semibold text-[#111827]">Thin lens equation simulator</p>
        </div>
        <p className="mt-2 text-[13px] leading-6 text-[#667085]">
          Adjust focal length and object distance to see how the image shifts between real and virtual formation.
        </p>
      </div>

      <div className="grid gap-5 px-5 py-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[24px] border border-black/[0.06] bg-[#0f172a] px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
          <svg viewBox="0 0 520 240" className="h-auto w-full">
            <defs>
              <marker id="lens-arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse">
                <path d="M0 0L8 4L0 8Z" fill="currentColor" />
              </marker>
            </defs>

            <rect x="0" y="0" width="520" height="240" rx="20" fill="#0f172a" />
            <line x1="36" y1={axisY} x2="484" y2={axisY} stroke="#94a3b8" strokeWidth="1.5" opacity="0.65" />
            <line x1={lensX} y1="28" x2={lensX} y2="212" stroke="#7dd3fc" strokeWidth="3" opacity="0.9" />

            <line
              x1={objectX}
              y1={axisY}
              x2={objectX}
              y2={objectTipY}
              stroke="#f8fafc"
              strokeWidth="3"
              markerEnd="url(#lens-arrow)"
            />

            <circle cx={principalFocusLeft} cy={axisY} r="3.5" fill="#f59e0b" />
            <circle cx={principalFocusRight} cy={axisY} r="3.5" fill="#f59e0b" />

            {imageDistance !== null ? (
              <line
                x1={imageX}
                y1={imageBottomY}
                x2={imageX}
                y2={imageTipY}
                stroke={imageDistance >= 0 ? "#34d399" : "#f472b6"}
                strokeWidth="3"
                markerEnd="url(#lens-arrow)"
              />
            ) : null}

            {showRays ? (
              <>
                <line x1={objectTipX} y1={objectTipY} x2={lensX} y2={objectTipY} stroke="#f8fafc" strokeWidth="1.5" />
                {imageDistance === null ? (
                  <line
                    x1={lensX}
                    y1={objectTipY}
                    x2="478"
                    y2={objectTipY}
                    stroke="#f8fafc"
                    strokeWidth="1.5"
                    opacity="0.55"
                    strokeDasharray="4 5"
                  />
                ) : imageDistance >= 0 ? (
                  <line
                    x1={lensX}
                    y1={objectTipY}
                    x2={imageX}
                    y2={imageTipY}
                    stroke="#a78bfa"
                    strokeWidth="1.5"
                  />
                ) : (
                  <>
                    <line
                      x1={lensX}
                      y1={objectTipY}
                      x2="478"
                      y2={axisY + ((478 - lensX) * (objectTipY - axisY)) / (principalFocusRight - lensX)}
                      stroke="#a78bfa"
                      strokeWidth="1.5"
                    />
                    <line
                      x1={lensX}
                      y1={objectTipY}
                      x2={imageX}
                      y2={imageTipY}
                      stroke="#a78bfa"
                      strokeWidth="1.5"
                      opacity="0.55"
                      strokeDasharray="4 5"
                    />
                  </>
                )}

                <line
                  x1={objectTipX}
                  y1={objectTipY}
                  x2={lensX}
                  y2={axisY}
                  stroke="#c4b5fd"
                  strokeWidth="1.5"
                />
                {imageDistance !== null ? (
                  <line
                    x1={lensX}
                    y1={axisY}
                    x2={imageX}
                    y2={imageTipY}
                    stroke="#c4b5fd"
                    strokeWidth="1.5"
                    strokeDasharray={imageDistance >= 0 ? undefined : "4 5"}
                  />
                ) : null}
              </>
            ) : null}

            <text x={objectX - 16} y={axisY + 24} fill="#cbd5e1" fontSize="12">
              object
            </text>
            <text x={lensX - 12} y="24" fill="#7dd3fc" fontSize="12">
              lens
            </text>
            <text x={principalFocusLeft - 10} y={axisY + 22} fill="#fbbf24" fontSize="12">
              F
            </text>
            <text x={principalFocusRight - 10} y={axisY + 22} fill="#fbbf24" fontSize="12">
              F
            </text>
            {imageDistance !== null ? (
              <text x={imageX - 16} y={axisY + 24} fill={imageDistance >= 0 ? "#6ee7b7" : "#f9a8d4"} fontSize="12">
                image
              </text>
            ) : null}
          </svg>
        </div>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[22px] border border-black/[0.06] bg-white px-4 py-4 shadow-[0_14px_32px_rgba(15,23,42,0.05)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Image distance</p>
              <p className="mt-2 text-[26px] font-semibold text-[#111827]">{formatDistance(imageDistance, units)}</p>
            </div>
            <div className="rounded-[22px] border border-black/[0.06] bg-white px-4 py-4 shadow-[0_14px_32px_rgba(15,23,42,0.05)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Image type</p>
              <p className="mt-2 text-[26px] font-semibold text-[#111827]">{imageKind}</p>
            </div>
          </div>

          <div className="rounded-[24px] border border-black/[0.06] bg-white px-4 py-4 shadow-[0_14px_32px_rgba(15,23,42,0.05)]">
            <div className="space-y-4">
              <label className="block">
                <div className="mb-2 flex items-center justify-between text-[12px] font-medium text-[#344054]">
                  <span>Focal length</span>
                  <span>{focal.toFixed(1)} {units}</span>
                </div>
                <input
                  type="range"
                  min="2"
                  max="40"
                  step="0.5"
                  value={focal}
                  onChange={(event) => setFocal(Number(event.target.value))}
                  className="h-2 w-full cursor-pointer accent-[#3151a6]"
                />
              </label>

              <label className="block">
                <div className="mb-2 flex items-center justify-between text-[12px] font-medium text-[#344054]">
                  <span>Object distance</span>
                  <span>{object.toFixed(1)} {units}</span>
                </div>
                <input
                  type="range"
                  min="2"
                  max="80"
                  step="0.5"
                  value={object}
                  onChange={(event) => setObject(Number(event.target.value))}
                  className="h-2 w-full cursor-pointer accent-[#111827]"
                />
              </label>
            </div>
          </div>

          <div className="rounded-[24px] border border-black/[0.06] bg-[#f8fafc] px-4 py-4 text-[13px] leading-6 text-[#475467]">
            <p className="font-medium text-[#111827]">Equation</p>
            <p className="mt-1">1/f = 1/dₒ + 1/dᵢ</p>
            <p className="mt-2">
              Magnification: {magnification === null ? "undefined at infinity" : magnification.toFixed(2)}.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export { LensEquationWidget };
export type { LensWidgetProps };
