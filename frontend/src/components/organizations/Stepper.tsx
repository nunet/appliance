import { useEffect, useRef } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import type { StepState } from "../../components/organizations/OnboardFlow";

/** Stepper */
export function Stepper({
  steps,
  currentIndex,
  currentStep = "init",
}: {
  steps: StepState[];
  currentIndex: number;
  currentStep: "complete" | "rejected" | string; // currentStep controls last one
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Scroll into view whenever the index changes
  useEffect(() => {
    const container = containerRef.current;
    const el = stepRefs.current[currentIndex];
    if (!container || !el) return;

    const containerWidth = container.clientWidth;
    const elCenter = el.offsetLeft + el.offsetWidth / 2;

    // desired scroll so that elCenter is in middle of container
    let targetScrollLeft = elCenter - containerWidth / 2;

    // clamp so we never overscroll beyond first or last
    targetScrollLeft = Math.max(
      0,
      Math.min(targetScrollLeft, container.scrollWidth - containerWidth)
    );

    container.scrollTo({
      left: targetScrollLeft,
      behavior: "smooth",
    });
  }, [currentIndex]);

  // filter out rejected or complete depending on currentStep
  const filteredSteps = steps.filter((s) => {
    if (currentStep === "complete" && s.id === "rejected") return false;
    if (currentStep === "rejected" && s.id === "complete") return false;
    return true;
  });

  return (
    <div ref={containerRef} className="w-full overflow-x-auto py-4">
      <div className="flex items-center gap-4 min-w-max">
        {filteredSteps.map((s, i) => {
          const isLast = i === filteredSteps.length - 1;

          const isRejected = isLast
            ? currentStep === "rejected"
            : s.state === "rejected";

          const isDone = isLast
            ? currentStep === "complete"
            : s.state === "done";

          const isActive = !isRejected && !isDone && s.state === "active";

          return (
            <div
              key={s.id}
              ref={(el) => (stepRefs.current[i] = el)}
              className="flex items-center gap-2"
            >
              <div
                className={[
                  "w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold border transition-all",
                  isRejected
                    ? "bg-red-600 text-white border-red-600"
                    : isActive
                    ? "bg-primary text-primary-foreground border-primary"
                    : isDone
                    ? "bg-green-600 text-white border-green-600"
                    : "bg-muted text-muted-foreground border-muted",
                ].join(" ")}
                title={s.virtual ? `${s.label} (virtual)` : s.label}
              >
                {isRejected ? (
                  <XCircle className="w-5 h-5" />
                ) : isDone ? (
                  <CheckCircle2 className="w-5 h-5" />
                ) : (
                  i + 1
                )}
              </div>
              <div className="text-xs whitespace-nowrap">
                <div className="font-medium">{s.label}</div>
              </div>
              {i !== filteredSteps.length - 1 && (
                <div className="w-10 h-px bg-border" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
