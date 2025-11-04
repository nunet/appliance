import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import type {
  ContractCreatePayload,
  ContractTemplateDetail,
} from "@/api/contracts";

const EMPTY_CONTRACT_TEMPLATE = "{\n  \n}";

export interface ContractCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: ContractCreatePayload) => Promise<void> | void;
  isSubmitting?: boolean;
  template?: ContractTemplateDetail | null;
}

function parseExtraArgs(value: string): string[] | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  return trimmed.split(/\s+/);
}

export function ContractCreateDialog({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
  template,
}: ContractCreateDialogProps) {
  const [destination, setDestination] = React.useState("");
  const [organizationDid, setOrganizationDid] = React.useState("");
  const [contractText, setContractText] = React.useState<string>(EMPTY_CONTRACT_TEMPLATE);
  const [extraArgsInput, setExtraArgsInput] = React.useState<string>("");

  const templateOrganizations = template?.organizations ?? [];

  React.useEffect(() => {
    if (!open) {
      setDestination("");
      setOrganizationDid("");
      setContractText(EMPTY_CONTRACT_TEMPLATE);
      setExtraArgsInput("");
      return;
    }

    if (template) {
      setDestination(template.default_destination ?? "");
      setOrganizationDid(template.organization_did ?? "");
      setContractText(JSON.stringify(template.contract, null, 2));
    } else {
      setDestination("");
      setOrganizationDid("");
      setContractText(EMPTY_CONTRACT_TEMPLATE);
    }
    setExtraArgsInput("");
  }, [open, template]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const trimmedDestination = destination.trim();
    const trimmedOrg = organizationDid.trim();

    if (!template && trimmedDestination.length === 0) {
      toast.error("Destination DID is required when creating a custom contract.");
      return;
    }

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(contractText) as Record<string, unknown>;
    } catch (error) {
      console.error("Invalid contract JSON", error);
      toast.error("Contract JSON must be valid.");
      return;
    }

    const payload: ContractCreatePayload = {
      contract: parsed,
      extra_args: parseExtraArgs(extraArgsInput),
    };

    if (trimmedDestination.length > 0) {
      payload.destination = trimmedDestination;
    }
    if (trimmedOrg.length > 0) {
      payload.organization_did = trimmedOrg;
    }
    if (template?.template_id) {
      payload.template_id = template.template_id;
    }

    try {
      await onSubmit(payload);
      onOpenChange(false);
    } catch (error) {
      // Let parent mutation toast details, but ensure dialog stays open.
      console.error("Failed to create contract", error);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl" showCloseButton>
        <DialogHeader>
          <DialogTitle>Create contract</DialogTitle>
          <DialogDescription>
            Craft a new contract manually or start from a template. Destination and organization can be overridden here.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          {template ? (
            <div className="space-y-3 rounded-lg border border-border/60 bg-muted/40 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm font-semibold leading-none">{template.name}</p>
                  {template.description ? (
                    <p className="text-xs text-muted-foreground">{template.description}</p>
                  ) : null}
                </div>
                <Badge variant="outline" className="uppercase">
                  {template.source}
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
                <span>Template</span>
                <Badge variant="outline" className="font-mono text-[11px]">
                  {template.template_id}
                </Badge>
                {template.origin ? <span className="text-muted-foreground">• {template.origin}</span> : null}
              </div>
              {template.default_destination ? (
                <p className="text-xs text-muted-foreground">
                  Default destination:{" "}
                  <span className="font-medium text-foreground">{template.default_destination}</span>
                </p>
              ) : null}
              {templateOrganizations.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted-foreground">Suggested organizations:</span>
                  {templateOrganizations.map((org) => (
                    <Button
                      key={org}
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setOrganizationDid(org)}
                      className="h-7 px-2 text-xs"
                    >
                      {org}
                    </Button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border/60 px-4 py-3 text-xs text-muted-foreground">
              No template selected. Provide the contract JSON and destination manually, or choose a template to
              pre-fill these fields.
            </div>
          )}

          <Separator />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="contract-destination">
                Destination DID {template ? <span className="text-muted-foreground">(optional)</span> : null}
              </Label>
              <Input
                id="contract-destination"
                placeholder="did:..."
                value={destination}
                onChange={(event) => setDestination(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Leave blank to use the template&apos;s default destination, or specify a custom DID.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="contract-organization">
                Organization DID <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="contract-organization"
                placeholder="did:org:..."
                value={organizationDid}
                onChange={(event) => setOrganizationDid(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Overrides the template&apos;s organization mapping when provided.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="contract-json">Contract payload (JSON)</Label>
            <textarea
              id="contract-json"
              className="min-h-[260px] w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={contractText}
              onChange={(event) => setContractText(event.target.value)}
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground">
              Review and adjust the contract payload before submitting.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="contract-extra-args">
              Extra CLI arguments <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="contract-extra-args"
              placeholder="--flag value"
              value={extraArgsInput}
              onChange={(event) => setExtraArgsInput(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Space-separated arguments forwarded to the DMS contract creation command.
            </p>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting} className="gap-2">
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                "Create contract"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
