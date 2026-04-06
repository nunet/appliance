// components/ui/RefreshButton.tsx
import { Loader2, RotateCw } from "lucide-react";
import { useState } from "react";
import { Button } from "./button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";
import { toast } from "sonner";

interface RefreshButtonProps {
  onClick: () => void | Promise<void>;
  isLoading: boolean;
  tooltip: string;
  children?: React.ReactNode;
}

export function RefreshButton({
  onClick,
  isLoading,
  tooltip,
  children,
}: RefreshButtonProps) {
  const [isPending, setIsPending] = useState(false);
  const showLoading = isLoading || isPending;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              if (showLoading) return;
              setIsPending(true);
              try {
                await onClick(); // wait for the refresh to finish
                toast.success("Page refreshed");
              } catch (error) {
                console.error("Error in RefreshButton onClick:", error);
                toast.error("Failed to refresh");
              } finally {
                setIsPending(false);
              }
            }}
            disabled={showLoading}
            className="flex items-center gap-2"
          >
            {showLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {children}
              </>
            ) : (
              <>
                <RotateCw className="w-4 h-4" />
                {children}
              </>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
