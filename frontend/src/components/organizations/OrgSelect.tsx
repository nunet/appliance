import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "../ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "../ui/card";

/** Select organization */
export function OrgSelect({
  known,
  onSelect,
  disabled,
}: {
  known: Record<string, any>;
  onSelect: (did: string) => void;
  disabled?: boolean;
}) {
  const [selected, setSelected] = useState<string>("");
  const orgEntries = Object.entries(known ?? {});

  const handleSelect = (did: string) => {
    setSelected(did);
    onSelect(did);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Select Organization</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {orgEntries.map(([key, val]) => {
              const isSelected = selected === key;
              return (
                <div
                  key={key}
                  onClick={() => handleSelect(key)}
                  className={`relative p-4 rounded-2xl cursor-pointer border transition-all duration-300 overflow-hidden
                    ${
                      isSelected
                        ? "border-blue-500 shadow-lg"
                        : "border-gray-200"
                    }
                  `}
                >
                  {/* Gradient overlay if selected */}
                  {isSelected && (
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-blue-500/30 to-transparent pointer-events-none" />
                  )}

                  <div className="relative z-10 flex flex-col">
                    <span className="font-medium">{val?.name ?? key}</span>
                    <span className="text-xs opacity-70 mt-2" title={key}>
                      {"..." + key.slice(-15)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
        <CardFooter></CardFooter>
      </Card>
    </div>
  );
}
