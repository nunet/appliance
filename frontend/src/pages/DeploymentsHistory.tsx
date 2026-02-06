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
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";

export default function Page() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isPruning, setIsPruning] = useState(false);
  const [isPruneDialogOpen, setIsPruneDialogOpen] = useState(false);
  const toastStyles = {
    className: "text-white [&_*]:!text-white",
    descriptionClassName: "text-white/90",
  };

  // 👇 tracks whether ["deployments"] is fetching
  const isFetchingDeployments =
    useIsFetching({ queryKey: ["deployments"] }) > 0;

  const handleRefresh = () => {
    queryClient.refetchQueries({ queryKey: ["deployments"] });
  };

  const handlePruneAll = async () => {
    setIsPruning(true);
    try {
      const res = await pruneDeployments({ all: true });
      toast.success("Deployments purged", {
        description: res.message || "Completed/failed deployments removed.",
        ...toastStyles,
      });
      queryClient.refetchQueries({ queryKey: ["deployments"] });
    } catch (error: any) {
      toast.error("Purge failed", {
        description: error?.response?.data?.message || "An unexpected error occurred",
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
                          data-testid="deployments-refresh-button"
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
                          onClick={() => setIsPruneDialogOpen(true)}
                          disabled={isPruning}
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
                        Purge completed/failed deployments
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <Button
                    variant="outline"
                    className="border-green-500 text-green-500 hover:bg-green-50 hover:text-green-600 flex items-center gap-2"
                    onClick={() => navigate("/deploy/new")}
                    data-testid="deployments-new-button"
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
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Purge deployments?</DialogTitle>
            <DialogDescription>
              This will delete all completed/failed deployments from DMS.
            </DialogDescription>
          </DialogHeader>
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
              disabled={isPruning}
            >
              {isPruning ? "Purging..." : "Purge"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
