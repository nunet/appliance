import { useState } from "react";
import { toast } from "sonner";
import { Button } from "../ui/button";
import { restartDms } from "../../api/api";
import { AlertTriangle, Loader2 } from "lucide-react";
import { organizationsApi } from "../../api/organizations";

function RestartDmsButton({
  qc,
  setStartOperation,
}: {
  qc: any;
  setStartOperation: (val: boolean) => void;
}) {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleRestart = async () => {
    setIsLoading(true);
    try {
      await restartDms();
      setStartOperation(false);
      toast.success("DMS is restarting");
      organizationsApi.reset().then(() => {
        qc.invalidateQueries({ queryKey: ["org-status"] });
      });
    } catch (err) {
      toast.error("Failed to restart DMS");
    } finally {
      setIsLoading(false);
      setIsConfirming(false);
    }
  };

  return (
    <>
      <p className="text-grey-200 text-sm my-3">
        You have to restart DMS for all new changes to apply.
      </p>
      {!isConfirming ? (
        <Button
          className="w-full bg-white text-black border border-gray-300 hover:bg-gray-50 mt-4"
          onClick={() => setIsConfirming(true)}
          disabled={isLoading}
        >
          {isLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          Restart DMS
        </Button>
      ) : (
        <div className="space-y-3 border border-red-300 rounded-lg p-3 mt-4">
          <div className="flex items-center gap-2 text-white">
            <AlertTriangle className="w-5 h-5" />
            <span>
              You are about to restart DMS. Be aware that any running jobs might
              be stopped.
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              className="flex-1 bg-red-500 text-white hover:bg-red-600"
              onClick={handleRestart}
              disabled={isLoading}
            >
              {isLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Yes, Restart
            </Button>
            <Button
              className="flex-1"
              variant="outline"
              onClick={() => setIsConfirming(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </>
  );
}

export default RestartDmsButton;
