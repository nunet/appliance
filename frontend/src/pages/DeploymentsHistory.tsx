import { RotateCw, Plus, Loader2, Trash2 } from "lucide-react";
import { useQueryClient, useIsFetching } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import DeploymentsTable from "../components/deployments/DeploymentsTable";
import { Button } from "../components/ui/button";
import { Card, CardTitle } from "../components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";
import { pruneDeployments } from "@/api/deployments";
import { toast } from "sonner";
import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "../components/ui/radio-group";
import { Input } from "../components/ui/input";
import { combineLocalDateAndTimeToUtcIso } from "@/utils/datetime";

export default function Page() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isPruning, setIsPruning] = useState(false);
  const [isPruneDialogOpen, setIsPruneDialogOpen] = useState(false);
  const [countdown, setCountdown] = useState(10);
  const [purgeMode, setPurgeMode] = useState<"all" | "before">("all");
  const [cutoffDate, setCutoffDate] = useState<string>("");
  const [cutoffTime, setCutoffTime] = useState<string>("23:59");
  const [quickSelectedDays, setQuickSelectedDays] = useState<number | null>(null);
  const isFormValid = purgeMode === "all" || (purgeMode === "before" && !!cutoffDate);
  const toastStyles = {
    className: "text-white [&_*]:!text-white",
    descriptionClassName: "text-white/90",
  };

  // Ref to return focus to the toolbar Purge button after dialog closes
  const purgeButtonRef = useRef<HTMLButtonElement | null>(null);

  // Helpers for quick-select chips
  const toLocalDateInputValue = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const handleQuickSelect = (days: number) => {
    const d = new Date();
    d.setDate(d.getDate() - days);
    setPurgeMode("before");
    setCutoffDate(toLocalDateInputValue(d));
    setCutoffTime("23:59");
    setQuickSelectedDays(days);
  };

  // 👇 tracks whether ["deployments"] is fetching
  const isFetchingDeployments =
    useIsFetching({ queryKey: ["deployments"] }) > 0;

  // Reset countdown whenever dialog opens or selection changes
  useEffect(() => {
    if (!isPruneDialogOpen) return;
    setCountdown(10);
  }, [isPruneDialogOpen, purgeMode, cutoffDate, cutoffTime]);

  // Start ticking only when form is valid
  useEffect(() => {
    if (!isPruneDialogOpen || !isFormValid || countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [isPruneDialogOpen, isFormValid, countdown]);

  const handleOpenPruneDialog = () => {
    if (isFetchingDeployments) {
      toast.info("Refreshing deployments… Please wait.");
      return;
    }
    // Aggregate across all deployment query cache entries (active only)
    const entries = queryClient.getQueriesData<any>({
      queryKey: ["deployments"],
      type: "active",
    });

    let total = 0;
    for (const [, data] of entries) {
      if (!data) continue;
      if (Array.isArray(data)) {
        total += data.length;
      } else if (Array.isArray(data.deployments)) {
        total += data.deployments.length;
      } else if (Array.isArray(data.items)) {
        total += data.items.length;
      } else if (typeof data.count === "number") {
        total += data.count;
      }
    }

    if (total === 0) {
      toast.info("The deployment history is already empty.");
      return;
    }

    setIsPruneDialogOpen(true);
  };

  const handleRefresh = () => {
    queryClient.refetchQueries({ queryKey: ["deployments"] });
  };

  const handlePruneAll = async () => {
    setIsPruning(true);
    try {
      let res: any;
      if (purgeMode === "before") {
        const isoCutoff = combineLocalDateAndTimeToUtcIso(
          cutoffDate,
          cutoffTime && cutoffTime.trim() ? cutoffTime : "23:59"
        );
        res = await pruneDeployments({ before: isoCutoff });
      } else {
        res = await pruneDeployments({ all: true });
      }

      if (res?.status === "success" || res?.ok === true) {
        const description =
          purgeMode === "before"
            ? (() => {
                const iso = combineLocalDateAndTimeToUtcIso(
                  cutoffDate,
                  cutoffTime && cutoffTime.trim() ? cutoffTime : "23:59"
                );
                const localDisplay = new Date(iso).toLocaleString();
                return `Deployments prior to ${localDisplay} removed.`;
              })()
            : "All deployments removed.";
        toast.success("Deployments purged", {
          description,
          ...toastStyles,
        });
        await queryClient.invalidateQueries({ queryKey: ["deployments"] });
        await queryClient.refetchQueries({ queryKey: ["deployments"], type: "active" });
        queryClient.removeQueries({ queryKey: ["deployments"], type: "inactive" });
      } else {
        toast.error("Purge failed", {
          description: res?.message || res?.error || "An unexpected error occurred",
        });
      }
    } catch (error: any) {
      toast.error("Purge failed", {
        description: error?.response?.data?.message || error?.message || "An unexpected error occurred",
      });
    } finally {
      setIsPruning(false);
      setIsPruneDialogOpen(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 lg:px-6 items-start">
            <Card className="lg:col-span-3 px-3">
              <div className="flex items-center justify-between mb-4">
                <CardTitle>Deployments</CardTitle>
                <div className="flex gap-2">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          className="flex items-center gap-2"
                          onClick={handleRefresh}
                          disabled={isFetchingDeployments} // disable while loading
                        >
                          {isFetchingDeployments ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <RotateCw className="w-4 h-4" />
                          )}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">
                        Refresh deployments
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="destructive"
                          className="flex items-center gap-2"
                          onClick={handleOpenPruneDialog}
                          disabled={isPruning}
                          ref={purgeButtonRef}
                        >
                          {isPruning ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                          Purge
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">
                        Clean deployment history
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <Button
                    variant="outline"
                    className="border-green-500 text-green-500 hover:bg-green-50 hover:text-green-600 flex items-center gap-2"
                    onClick={() => navigate("/deploy/new")}
                  >
                    <Plus className="w-4 h-4" />
                    New
                  </Button>
                </div>
              </div>
              <DeploymentsTable />
            </Card>
          </div>
        </div>
      </div>

      <Dialog
        open={isPruneDialogOpen}
        onOpenChange={(open) => {
          if (!open && !isPruning) {
            setIsPruneDialogOpen(false);
            // Return focus to the toolbar Purge button for accessibility
            setTimeout(() => {
              purgeButtonRef.current?.focus();
            }, 0);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Are you sure?</DialogTitle>
            <DialogDescription asChild>
              <div>
                <p>
                  This will delete deployments. You will lose access
                  to:
                </p>
                <ul className="list-disc space-y-1 pl-5 mt-2">
                  <li>History</li>
                  <li>Logs</li>
                  <li>Progress</li>
                </ul>
              </div>
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 space-y-3">
            <p className="text-sm text-muted-foreground">
              Choose what to delete:
            </p>
            <RadioGroup
              value={purgeMode}
              onValueChange={(v) => {
                setPurgeMode(v as "all" | "before");
                if (v !== "before") {
                  setQuickSelectedDays(null);
                }
              }}
              className="space-y-2"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem id="purge-mode-all" value="all" />
                <label
                  htmlFor="purge-mode-all"
                  className="text-sm font-medium leading-none"
                >
                  All deployments
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem id="purge-mode-before" value="before" />
                <label
                  htmlFor="purge-mode-before"
                  className="text-sm font-medium leading-none"
                >
                  Deployments before…
                </label>
              </div>
            </RadioGroup>

            {purgeMode === "before" && (
              <div className="space-y-3 pt-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label htmlFor="cutoff-date" className="text-sm font-medium leading-none">
                      Date
                    </label>
                    <Input
                      id="cutoff-date"
                      type="date"
                      value={cutoffDate}
                      onChange={(e) => {
                        setCutoffDate(e.target.value);
                        setQuickSelectedDays(null);
                      }}
                      aria-describedby="cutoff-date-help"
                    />
                    <p id="cutoff-date-help" className="text-xs text-muted-foreground">
                      Select a date to purge deployments created before that point.
                    </p>
                    {!cutoffDate && (
                      <p className="text-xs text-destructive/90" role="alert">Select a date</p>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label htmlFor="cutoff-time" className="text-sm font-medium leading-none">
                      Time
                    </label>
                    <Input
                      id="cutoff-time"
                      type="time"
                      value={cutoffTime}
                      onChange={(e) => {
                        setCutoffTime(e.target.value);
                        setQuickSelectedDays(null);
                      }}
                      aria-describedby="cutoff-time-help"
                    />
                    <p id="cutoff-time-help" className="text-xs text-muted-foreground">
                      Times are in your local timezone; the server uses UTC.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <span className="text-xs text-muted-foreground pr-1">Quick select:</span>
                  <Button size="sm" variant={quickSelectedDays === 30 ? "default" : "outline"} aria-pressed={quickSelectedDays === 30} onClick={() => handleQuickSelect(30)}>30 days ago</Button>
                  <Button size="sm" variant={quickSelectedDays === 60 ? "default" : "outline"} aria-pressed={quickSelectedDays === 60} onClick={() => handleQuickSelect(60)}>60 days ago</Button>
                  <Button size="sm" variant={quickSelectedDays === 90 ? "default" : "outline"} aria-pressed={quickSelectedDays === 90} onClick={() => handleQuickSelect(90)}>90 days ago</Button>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsPruneDialogOpen(false)}
              disabled={isPruning}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handlePruneAll}
              disabled={isPruning || countdown > 0 || (purgeMode === "before" && !cutoffDate)}
            >
              {isPruning ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Purging
                </>
              ) : isFormValid && countdown > 0 ? (
                `Purge (${countdown})`
              ) : (
                "Purge"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
