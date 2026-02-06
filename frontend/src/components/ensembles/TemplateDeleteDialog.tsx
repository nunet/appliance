import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { deleteTemplate } from "@/api/ensembles";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type TemplateDeleteDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templatePath?: string | null;
  templateName?: string | null;
  onDeleted?: () => void;
};

export function TemplateDeleteDialog({
  open,
  onOpenChange,
  templatePath,
  templateName,
  onDeleted,
}: TemplateDeleteDialogProps) {
  const { mutateAsync, isPending } = useMutation({
    mutationFn: async () => {
      if (!templatePath) throw new Error("No template selected");
      return deleteTemplate(templatePath);
    },
    onSuccess: () => {
      toast.success("Template deleted");
      onDeleted?.();
      onOpenChange(false);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      toast.error(detail || "Failed to delete template");
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !isPending && onOpenChange(next)}>
      <DialogContent data-testid="ensemble-delete-dialog">
        <DialogHeader>
          <DialogTitle>Delete template</DialogTitle>
          <DialogDescription>
            {templateName
              ? `This will remove "${templateName}" and its JSON form.`
              : "This will remove the selected template and its JSON form."}
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground break-all">
          {templatePath}
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
            data-testid="ensemble-delete-cancel"
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => mutateAsync()}
            disabled={isPending || !templatePath}
            data-testid="ensemble-delete-confirm"
          >
            {isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
