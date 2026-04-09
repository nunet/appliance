import { useCallback, useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card";
import { organizationsApi } from "../../api/organizations";
import { Circle, Loader2, RefreshCw } from "lucide-react";
import { ExpiryCard } from "./ExpiryDate";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { toast } from "sonner";


/** Select organization */
export function OrgSelect({
  known,
  onSelect,
  disabled,
  setStartOperation,
  onBeginOnboarding,
  onRenew,
}: {
  known: Record<string, any>;
  onSelect: (did: string) => void;
  disabled?: boolean;
  setStartOperation: (val: boolean) => void;
  onBeginOnboarding?: () => void;
  onRenew?: (did: string) => void;
}) {
  const [joinedOrgs, setJoinedOrgs] = useState<string[]>([]);
  const [orgData, setOrgData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [leaveTarget, setLeaveTarget] = useState<{ did: string; name?: string } | null>(null);
  const queryClient = useQueryClient();

  const refreshKnownMutation = useMutation({
    mutationFn: organizationsApi.refreshKnownOrgs,
    onSuccess: async (res) => {
      const nextKnown = res?.known ?? {};
      queryClient.setQueryData(["orgs-known"], nextKnown);
      await queryClient.invalidateQueries({ queryKey: ["orgs-known"] });
    },
    onError: (err) => {
      console.error("Failed to refresh known organizations", err);
    },
  });

  const fetchJoined = useCallback(async () => {
    try {
      const data = await organizationsApi.getJoinedOrgs();
      setJoinedOrgs(data.map((org: any) => org.did));
      setOrgData(data);
    } catch (err) {
      console.error("Failed to fetch joined orgs", err);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        await fetchJoined();
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [fetchJoined]);

  const leaveMutation = useMutation({
    mutationFn: (did: string) => organizationsApi.leaveOrg(did),
    onSuccess: async (_data, _did) => {
      try {
        await fetchJoined();
        toast.success("Left organization successfully.");
      } finally {
        setLeaveTarget(null);
      }
    },
    onError: (err) => {
      console.error("Failed to leave organization", err);
      toast.error("Failed to leave organization. Please try again.");
    },
  });

  const orgEntries = Object.entries(known ?? {});
  const nowMs = Date.now();

  const handleJoin = (did: string) => {
    onSelect(did); // trigger join flow
    setStartOperation(true);
    onBeginOnboarding?.();
  };

  const handleRenew = (did: string) => {
    if (!onRenew) {
      handleJoin(did);
      return;
    }
    onRenew(did);
  };

  const handleRefreshKnown = async () => {
    try {
      await refreshKnownMutation.mutateAsync();
    } catch (err) {
      // Error handled in mutation onError for visibility in devtools/console
    }
  };

  if (loading) return <div>Loading organizations...</div>;

  return (
    <>
      <div className="space-y-4">
        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle>Select Organization</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefreshKnown}
              disabled={refreshKnownMutation.isPending}
              className="w-full sm:w-auto"
              data-testid="org-fetch-button"
            >
              {refreshKnownMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              Fetch Known Orgs
            </Button>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 gap-4 items-start">
              {orgEntries.map(([did, val]) => {
                const isJoined = joinedOrgs.includes(did);
                const matchedOrg = orgData.find((org) => org.did === did);
                const requiresWallet = Boolean(val?.tokenomics?.enabled);
                const expiryIso = typeof matchedOrg?.expiry === "string" ? matchedOrg.expiry : null;
                const expiryDate = expiryIso ? new Date(expiryIso) : null;
                const computedExpiresSoon =
                  expiryDate instanceof Date &&
                  !Number.isNaN(expiryDate.getTime()) &&
                  expiryDate.getTime() - nowMs <= 2 * 24 * 60 * 60 * 1000;
                const expiresSoon =
                  isJoined &&
                  (typeof matchedOrg?.expires_soon === "boolean"
                    ? matchedOrg.expires_soon
                    : computedExpiresSoon);

                return (
                  <div
                    key={did}
                    data-testid="org-card"
                    data-org-did={did}
                    data-org-name={val?.name ?? did}
                    className={`relative p-4 rounded-2xl border transition-all duration-300 overflow-hidden
                      ${isJoined ? "border-green-500" : "border-gray-200"}
                    `}
                  >
                    <div className="relative z-10 flex flex-col">
                      <div className="flex flex-row justify-between items-center">
                        <span className="font-medium">{val?.name ?? did}</span>
                        <div className="flex items-center gap-2">
                          {requiresWallet && (
                            <span className="inline-block px-2 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-full">
                              Wallet required
                            </span>
                          )}
                          {isJoined && (
                            <span className="inline-block px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                              Joined
                            </span>
                          )}
                          {expiresSoon && (
                            <span className="inline-block px-2 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-full">
                              Expires soon
                            </span>
                          )}
                        </div>
                      </div>

                      <span className="text-xs opacity-70 mt-2" title={did}>
                        {"..." + did.slice(-20)}
                      </span>
                      {isJoined && (
                        <>
                          <Card className="flex flex-col mt-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-muted/30 gap-3">
                            <CardTitle>Capabilities:</CardTitle>
                            <CardContent>
                              {(matchedOrg?.capabilities ?? []).map((cap: string) => (
                                <p className="flex flex-row align-middle items-center gap-3" key={cap}>
                                  <Circle size={10} />
                                  {cap}
                                </p>
                              ))}
                            </CardContent>
                          </Card>
                          <Card className="flex flex- mt-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-muted/30 gap-3">
                            <ExpiryCard orgData={orgData} did={did} />
                          </Card>
                        </>
                      )}
                      <div className="mt-4 w-full flex flex-col gap-2">
                        {!isJoined && (
                          <Button
                            size="sm"
                            onClick={() => handleJoin(did)}
                            disabled={disabled}
                            className="w-full cursor-pointer"
                            data-testid="org-join-button"
                            data-org-did={did}
                          >
                            Join
                          </Button>
                        )}
                        {isJoined && (
                          <>
                            {expiresSoon && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleRenew(did)}
                                disabled={disabled}
                                className="w-full cursor-pointer"
                                data-testid="org-renew-button"
                                data-org-did={did}
                              >
                                Renew
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => setLeaveTarget({ did, name: val?.name ?? did })}
                              disabled={disabled || leaveMutation.isPending}
                              className="w-full cursor-pointer"
                              data-testid="org-leave-button"
                              data-org-did={did}
                            >
                              Leave
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={!!leaveTarget}
        onOpenChange={(open) => {
          if (!open && !leaveMutation.isPending) {
            setLeaveTarget(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Leave organization?</DialogTitle>
            <DialogDescription>
              {leaveTarget
                ? `This will remove all capabilities associated with ${leaveTarget.name ?? leaveTarget.did}.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={leaveMutation.isPending}
              onClick={() => setLeaveTarget(null)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={leaveMutation.isPending || !leaveTarget}
              onClick={() => leaveTarget && leaveMutation.mutate(leaveTarget.did)}
              data-testid="org-leave-confirm-button"
            >
              {leaveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Leave
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
