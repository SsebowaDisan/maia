import { useEffect, useState } from "react";
import { useTypewriterText } from "./useTypewriterText";

type SystemSceneProps = {
  activeEventType: string;
  activeDetail: string;
  activeTitle: string;
  sceneText: string;
};

function SystemScene({ activeTitle }: SystemSceneProps) {
  const statusText = activeTitle || "Processing secure agent workflow";
  const [reduceMotion, setReduceMotion] = useState(false);
  const { typedText: typedStatusText, showCaret } = useTypewriterText(statusText, {
    charIntervalMs: 52,
    caretBlinkMs: 560,
    caret: true,
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduceMotion(mediaQuery.matches);
    sync();
    mediaQuery.addEventListener("change", sync);
    return () => mediaQuery.removeEventListener("change", sync);
  }, []);
  const pageScrollAnimation = `system-page-scroll ${reduceMotion ? "8.8s" : "4.9s"} linear infinite`;
  const pageSheenAnimation = `system-page-sheen ${reduceMotion ? "4.8s" : "2.6s"} ease-in-out infinite`;
  const cardWobbleAnimation = `system-card-wobble ${reduceMotion ? "6.8s" : "2.8s"} ease-in-out infinite`;
  const lineShiftAnimation = `system-line-shift ${reduceMotion ? "3.5s" : "1.7s"} ease-in-out infinite`;
  const lineWidthAnimation = `system-line-breathe ${reduceMotion ? "5.6s" : "2.4s"} ease-in-out infinite`;

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9">
      <style>{`
        @keyframes system-page-scroll {
          0% { transform: translateY(0); }
          100% { transform: translateY(-312px); }
        }
        @keyframes system-card-wobble {
          0%, 100% { transform: translateX(0px) scale(1); opacity: 0.98; }
          50% { transform: translateX(3px) scale(1.003); opacity: 1; }
        }
        @keyframes system-line-shift {
          0% { transform: translateX(-155%); opacity: 0.18; }
          25% { opacity: 0.36; }
          100% { transform: translateX(235%); opacity: 0.08; }
        }
        @keyframes system-line-breathe {
          0%, 100% { transform: scaleX(0.76); }
          50% { transform: scaleX(1); }
        }
        @keyframes system-page-sheen {
          0% { transform: translateX(-125%); opacity: 0.05; }
          35% { opacity: 0.18; }
          100% { transform: translateX(140%); opacity: 0.04; }
        }
      `}</style>
      <div className="mx-auto flex h-full w-full max-w-[840px] flex-col overflow-hidden rounded-[14px] border border-black/10 bg-white shadow-[0_22px_48px_-34px_rgba(17,24,39,0.45)]">
        <div className="flex h-[44px] shrink-0 items-center justify-center border-b border-[#ebedf2] px-4">
          <p className="text-[13px] font-medium text-[#5b6472]">Agent workspace</p>
        </div>
        <div className="relative flex flex-1 flex-col overflow-hidden px-8 py-6">
          <div
            className={`pointer-events-none absolute -right-24 -top-20 h-64 w-64 rounded-full bg-[#7ca7ff]/25 blur-3xl ${reduceMotion ? "opacity-55" : "animate-[pulse_7.8s_ease-in-out_infinite]"}`}
          />
          <div
            className={`pointer-events-none absolute -left-20 bottom-[-80px] h-56 w-56 rounded-full bg-[#b4ccff]/28 blur-3xl ${reduceMotion ? "opacity-45" : "animate-[pulse_9.4s_ease-in-out_infinite]"}`}
            style={!reduceMotion ? { animationDelay: "720ms" } : undefined}
          />
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">System activity</p>
          <p className="relative z-10 mt-2 max-w-[680px] text-[clamp(18px,2.35vw,29px)] font-semibold leading-[1.18] tracking-[-0.012em] text-[#4a5160]">
            {typedStatusText || "\u00A0"}
            <span className={`ml-[1px] inline-block w-[8px] text-[#64718a] ${showCaret ? "opacity-100" : "opacity-0"}`}>
              |
            </span>
          </p>
          <div className="relative z-10 mt-5 max-w-[640px] rounded-2xl border border-black/[0.1] bg-white/95 px-4 py-3.5 shadow-[0_18px_38px_-34px_rgba(17,24,39,0.55)]">
            <div className="flex items-center gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[#374151]">
                Orchestration
              </p>
            </div>
            <div className="mt-3">
              <div className="relative h-56 overflow-hidden rounded-xl border border-[#d4d9e3] bg-[linear-gradient(180deg,#f8fafc_0%,#f2f4f8_100%)] px-3 py-2.5">
                <div
                  className="pointer-events-none absolute inset-y-0 left-0 w-[22%] bg-[linear-gradient(90deg,rgba(255,255,255,0.32),rgba(255,255,255,0))]"
                  style={{ animation: pageSheenAnimation }}
                />
                <div
                  className="absolute inset-x-3 top-2.5 flex flex-col gap-2"
                  style={{ animation: pageScrollAnimation }}
                >
                  {[0, 1, 2, 0, 1, 2, 0, 1, 2].map((pattern, pageIndex) => (
                    (() => {
                      const widths =
                        pattern === 0 ? [78, 92, 60] : pattern === 1 ? [66, 74, 88] : [84, 68, 76];
                      const colors = ["#d7deea", "#dce3ef", "#e2e8f3"];
                      return (
                        <div
                          key={`system-page-${pattern}-${pageIndex}`}
                          className="relative overflow-hidden rounded-lg border border-[#cfd5df] bg-white px-2.5 py-2 shadow-[0_8px_20px_-18px_rgba(17,24,39,0.7)]"
                          style={{
                            animation: cardWobbleAnimation,
                            animationDelay: `${pageIndex * 160}ms`,
                          }}
                        >
                          <div
                            className="relative mb-1.5 h-[5px] w-[36%] overflow-hidden rounded-full bg-[#cfd8e6]"
                            style={{
                              transformOrigin: "left center",
                              animation: lineWidthAnimation,
                              animationDelay: `${pageIndex * 90}ms`,
                            }}
                          >
                            <span
                              className="absolute inset-y-0 left-0 w-[32%] rounded-full bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.88),rgba(255,255,255,0))]"
                              style={{
                                animation: lineShiftAnimation,
                                animationDelay: `${pageIndex * 110}ms`,
                              }}
                            />
                          </div>
                          <div className="space-y-1">
                            {widths.map((width, lineIndex) => (
                              <div
                                key={`system-page-line-${pageIndex}-${lineIndex}`}
                                className="relative h-[4px] overflow-hidden rounded-full"
                                style={{
                                  width: `${width}%`,
                                  backgroundColor: colors[lineIndex],
                                  transformOrigin: "left center",
                                  animation: lineWidthAnimation,
                                  animationDelay: `${pageIndex * 140 + lineIndex * 180}ms`,
                                }}
                              >
                                <span
                                  className="absolute inset-y-0 left-0 w-[30%] rounded-full bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.76),rgba(255,255,255,0))]"
                                  style={{
                                    animation: lineShiftAnimation,
                                    animationDelay: `${pageIndex * 120 + lineIndex * 140}ms`,
                                  }}
                                />
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div className="flex-1" />
        </div>
      </div>
    </div>
  );
}

type DefaultSceneProps = {
  isSystemScene: boolean;
  stageFileName: string;
};

function DefaultScene({ isSystemScene, stageFileName }: DefaultSceneProps) {
  return (
    <div className="absolute inset-0 px-4 py-3 text-white/85">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">{stageFileName}</span>
        <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">
          {isSystemScene ? "system" : "reading"}
        </span>
      </div>
      <div className="space-y-2">
        <div className="h-2 w-[88%] rounded-full bg-white/15" />
        <div className="h-2 w-[74%] rounded-full bg-white/10" />
        <div className="h-2 w-[91%] rounded-full bg-white/15" />
        <div className="h-2 w-[82%] rounded-full bg-white/10" />
        <div className="h-2 w-[66%] rounded-full bg-white/15" />
        <div className="h-2 w-[92%] rounded-full bg-white/10" />
      </div>
    </div>
  );
}

export { DefaultScene, SystemScene };
