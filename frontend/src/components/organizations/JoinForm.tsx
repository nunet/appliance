import { Loader2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "../ui/card";
import { Input } from "../ui/input";
import { RadioGroup, RadioGroupItem } from "../ui/radio-group";
import { Label } from "../ui/label";

export function JoinForm({
  orgDid,
  submitting,
  onSubmit,
  knownOrgs,
}: {
  orgDid?: string;
  knownOrgs?: Record<string, any>;
  submitting?: boolean;
  onSubmit: (data: Record<string, string>) => void;
}) {
  const [formData, setFormData] = useState<Record<string, string>>({
    name: "",
    wormhole: "",
    why_join: "provide", // default
  });

  if (!orgDid || !knownOrgs?.[orgDid]) {
    return null;
  }

  const org = knownOrgs[orgDid];
  const fields = org.join_fields ?? [];

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  // required fields check
  const canSubmit =
    formData["name"]?.trim() &&
    fields.every((f: any) => !f.required || formData[f.name]?.trim());

  return (
    <Card>
      <CardHeader>
        <CardTitle>Join {org.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* Always include name */}
          <Input
            value={formData["name"] ?? ""}
            onChange={(e) => handleChange("name", e.target.value)}
            placeholder="Full name"
          />

          {/* Dynamically render org fields */}
          {fields.map((field: any) => (
            <Input
              key={field.name}
              type={field.type}
              required={field.required}
              value={formData[field.name] ?? ""}
              onChange={(e) => handleChange(field.name, e.target.value)}
              placeholder={field.label}
              className={field.type === "text" ? "md:col-span-2" : ""}
            />
          ))}

          {/* Optional wormhole field */}
          <Input
            className="md:col-span-2"
            value={formData["wormhole"] ?? ""}
            onChange={(e) => handleChange("wormhole", e.target.value)}
            placeholder="Wormhole code"
          />
        </div>

        {/* Why Join - radio group */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Why Join?</Label>
          <RadioGroup
            value={formData["why_join"]}
            onValueChange={(v) => handleChange("why_join", v)}
            className="grid grid-cols-1 md:grid-cols-3 gap-2"
          >
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="provide" id="provide" />
              <Label htmlFor="provide">Provide Compute</Label>
            </div>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="access" id="access" />
              <Label htmlFor="access">Access Compute</Label>
            </div>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="both" id="both" />
              <Label htmlFor="both">Both</Label>
            </div>
          </RadioGroup>
        </div>
      </CardContent>
      <CardFooter>
        <Button
          className="w-full"
          disabled={!canSubmit || submitting}
          onClick={() => onSubmit(formData)}
        >
          {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          Submit
        </Button>
      </CardFooter>
    </Card>
  );
}
