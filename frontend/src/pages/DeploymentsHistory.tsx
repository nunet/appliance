import { RotateCw, Plus, Loader2 } from "lucide-react";
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

export default function Page() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // 👇 tracks whether ["deployments"] is fetching
  const isFetchingDeployments =
    useIsFetching({ queryKey: ["deployments"] }) > 0;

  const handleRefresh = () => {
    queryClient.refetchQueries({ queryKey: ["deployments"] });
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
    </div>
  );
}
