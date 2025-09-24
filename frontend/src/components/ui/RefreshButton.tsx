// components/ui/RefreshButton.tsx
import { Loader2, RotateCw } from "lucide-react";
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
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              try {
                await onClick(); // wait for the refresh to finish
                toast.success("Refreshed successfully");
              } catch (error) {
                console.error("Error in RefreshButton onClick:", error);
                toast.error("Failed to refresh");
              }
            }}
            disabled={isLoading}
            className="flex items-center gap-2"
          >
            {isLoading ? (
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
