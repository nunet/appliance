import { useEffect, useRef, useState } from "react";

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_MS = 300_000;

type PollTarget = "idle" | "until_onboarded" | "until_not_onboarded";

/**
 * After POST /dms/onboard or /dms/offboard succeeds, DMS may still report the previous
 * `onboarding_status` for a short time. Poll `allInfo` until the UI-derived onboarded flag matches.
 */
export function usePollApplianceInfoAfterStatusChange(
  isOnboarded: boolean,
  refetchInfo: () => Promise<unknown>
) {
  const [target, setTarget] = useState<PollTarget>("idle");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (target === "idle") {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      return;
    }

    const done =
      target === "until_onboarded" ? isOnboarded : !isOnboarded;
    if (done) {
      setTarget("idle");
      return;
    }

    // Run immediately — the POST handler already refetched once; DMS may still lag by a few seconds.
    void refetchInfo();
    intervalRef.current = setInterval(() => {
      void refetchInfo();
    }, POLL_INTERVAL_MS);
    timeoutRef.current = setTimeout(() => {
      setTarget("idle");
    }, POLL_MAX_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [target, isOnboarded, refetchInfo]);

  return {
    startPollingUntilOnboarded: () => setTarget("until_onboarded"),
    startPollingUntilNotOnboarded: () => setTarget("until_not_onboarded"),
  };
}
