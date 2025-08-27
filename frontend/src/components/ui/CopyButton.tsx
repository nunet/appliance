import { Button } from "@/components/ui/button";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export const CopyButton = ({ text, className }) => {
  const [smallCopy, setSmallCopy] = useState<boolean>(false);
  const handleRegularCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setSmallCopy(true);
    setTimeout(() => setSmallCopy(false), 4000);
  };

  return (
    <Button
      variant="outline"
      size="icon"
      className={cn(
        "h-7 w-7",
        className // append any extra classes passed from parent
      )}
      onClick={() => handleRegularCopy(text)}
    >
      {smallCopy ? (
        <Check className="w-3 h-3 text-green-600" />
      ) : (
        <Copy className="w-3 h-3" />
      )}
    </Button>
  );
};
