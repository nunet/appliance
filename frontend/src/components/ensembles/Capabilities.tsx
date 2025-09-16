// frontend/src/components/ensembles/Capabilities.tsx
import * as React from "react";
import { Badge } from "@/components/ui/badge";

type Props = {
  supports: Array<"local" | "targeted" | "non_targeted">;
  needsPeerId?: boolean;
  className?: string;
};

export default function Capabilities({ supports, needsPeerId, className }: Props) {
  const active = new Set(supports);
  return (
    <div className={`flex flex-wrap gap-2 ${className || ""}`}>
      <Badge variant={active.has("local") ? "default" : "secondary"}>local</Badge>
      <Badge variant={active.has("targeted") ? "default" : "secondary"}>
        targeted{needsPeerId ? " (peer_id)" : ""}
      </Badge>
      <Badge variant={active.has("non_targeted") ? "default" : "secondary"}>
        non_targeted
      </Badge>
    </div>
  );
}
