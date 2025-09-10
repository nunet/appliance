import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { uploadTemplate } from "@/api/ensembles";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUploaded?: (yamlPath: string) => void;
};

export default function TemplateUploadDialog({ open, onOpenChange, onUploaded }: Props) {
  const qc = useQueryClient();
  const [yamlFile, setYamlFile] = React.useState<File | null>(null);
  const [jsonFile, setJsonFile] = React.useState<File | null>(null);
  const [category, setCategory] = React.useState("");

  const submit = React.useCallback(async (confirmOverwrite: boolean) => {
    if (!yamlFile) throw new Error("Please choose a YAML file");
    const form = new FormData();
    form.append("file", yamlFile);
    if (jsonFile) form.append("sidecar", jsonFile);
    if (category) form.append("category", category);
    form.append("confirm_overwrite", String(confirmOverwrite));
    form.append("generate_json", "true"); // if no JSON given, backend will infer & save one
    return uploadTemplate(form);
  }, [yamlFile, jsonFile, category]);

  const { mutateAsync: doUpload, isPending: isUploading } = useMutation({
    mutationFn: async () => submit(false),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["yaml-templates"] });
      qc.invalidateQueries({ queryKey: ["form-templates"] });
      toast.success(res.message || "Template uploaded");
      if (res.yaml_path && onUploaded) onUploaded(res.yaml_path);
      onOpenChange(false);
      setYamlFile(null); setJsonFile(null); setCategory("");
    },
    onError: async (err: any) => {
      const detail = err?.response?.data?.detail;
      if (detail?.status === "confirm_overwrite") {
        const existsYaml = detail.existing_paths?.yaml;
        const existsJson = detail.existing_paths?.json;
        const yes = window.confirm(
          `A template with this name already exists${existsYaml ? ` (${existsYaml})` : ""}${
            existsJson ? ` and a sidecar (${existsJson})` : ""
          }.\nDo you want to replace it?`
        );
        if (yes) {
          try {
            const res2 = await submit(true);
            qc.invalidateQueries({ queryKey: ["yaml-templates"] });
            qc.invalidateQueries({ queryKey: ["form-templates"] });
            toast.success(res2.message || "Template replaced");
            if (res2.yaml_path && onUploaded) onUploaded(res2.yaml_path);
            onOpenChange(false);
            setYamlFile(null); setJsonFile(null); setCategory("");
          } catch (e: any) {
            toast.error(e?.response?.data?.detail || "Overwrite failed");
          }
        } else {
          toast.message("Upload cancelled.");
        }
        return;
      }
      if (detail?.status === "needs_input") {
        const prompts = detail.prompts || [];
        const lines = prompts.length
          ? prompts.map((p: any) => `• ${p.field} → ${p.required_keys?.join(", ")}`).join("\n")
          : "Additional details required.";
        toast.error(`More information needed to finalize the form:\n${lines}`);
        return;
      }
      toast.error(detail || "Upload failed");
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>Upload Ensemble</DialogTitle>
          <DialogDescription>
            Pick a YAML template. If you don’t have a JSON sidecar, we’ll generate one automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>YAML Template (.yaml/.yml)</Label>
            <Input type="file" accept=".yaml,.yml" onChange={(e) => setYamlFile(e.target.files?.[0] || null)} />
          </div>
          <div className="grid gap-2">
            <Label>Optional JSON Sidecar (.json)</Label>
            <Input type="file" accept=".json" onChange={(e) => setJsonFile(e.target.files?.[0] || null)} />
          </div>
          <div className="grid gap-2">
            <Label>Category (folder)</Label>
            <Input placeholder="rare-evo" value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>Cancel</Button>
          <Button onClick={() => doUpload()} disabled={isUploading || !yamlFile}>
            {isUploading ? "Uploading..." : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
