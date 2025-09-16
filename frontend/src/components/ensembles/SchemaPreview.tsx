// frontend/src/components/ensembles/SchemaPreview.tsx
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { getEffectiveSchema } from "@/api/ensembles";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import Capabilities from "./Capabilities";
import { useNavigate } from "react-router-dom";
import { FormSchema } from "@/types";

type Props = {
  templatePath: string;
};

export default function SchemaPreview({ templatePath }: Props) {
  const navigate = useNavigate();

  const { data: schema, isLoading } = useQuery<FormSchema>({
    queryKey: ["effective-schema", templatePath],
    queryFn: () => getEffectiveSchema(templatePath, "auto"),
    enabled: !!templatePath,
  });

  const fieldsEntries = schema ? Object.entries(schema.fields || {}) : [];
  const needsPeer = !!schema?.fields?.peer_id;
  const supports = needsPeer
    ? (["local", "targeted", "non_targeted"] as const)
    : (["non_targeted"] as const);

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-lg">
              {schema?.name || "Form Schema"}
            </CardTitle>
            {schema?.description && (
              <p className="text-sm text-muted-foreground">
                {schema.description}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => navigator.clipboard.writeText(templatePath)}
            >
              Copy YAML Path
            </Button>
            <Button onClick={() => navigate(`/deploy/new`)}>Use in Wizard</Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Capabilities
          supports={supports as any}
          needsPeerId={needsPeer}
          className="mt-1"
        />

        <Separator />

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading schema…</p>
        ) : fieldsEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This template has no configurable fields. You can still deploy it.
          </p>
        ) : (
          <div className="space-y-3">
            {fieldsEntries.map(([key, f]) => (
              <div
                key={key}
                className="border rounded-md p-3 flex items-start justify-between"
              >
                <div>
                  <div className="font-medium">{f.label || key}</div>
                  <div className="text-xs text-muted-foreground break-all">
                    <code>{key}</code>
                    {f.description ? ` — ${f.description}` : ""}
                  </div>
                  {f.category && (
                    <div className="mt-2">
                      <Badge variant="outline">{f.category}</Badge>
                    </div>
                  )}
                </div>
                <div className="text-right text-sm">
                  <div className="uppercase text-[10px] tracking-wide">
                    {f.type}
                  </div>
                  {f.required === false && (
                    <div className="text-xs text-muted-foreground">optional</div>
                  )}
                  {f.default !== undefined && (
                    <div className="text-xs text-muted-foreground">
                      default: {String(f.default)}
                    </div>
                  )}
                  {(f.min !== undefined || f.max !== undefined) && (
                    <div className="text-xs text-muted-foreground">
                      {f.min !== undefined ? `min ${f.min}` : ""}{" "}
                      {f.max !== undefined ? `max ${f.max}` : ""}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
