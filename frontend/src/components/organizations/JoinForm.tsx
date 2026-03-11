import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import { Tooltip, TooltipTrigger, TooltipContent } from "../ui/tooltip";
import { Badge } from "../ui/badge";
import { ConnectWalletButton } from "../payments/ConnectWalletButton";
import { useWalletStore, type WalletType } from "@/stores/walletStore";
import type { JoinSubmitPayload } from "../../api/organizations";

const DEFAULT_ROLE = "compute_provider";
const ROLE_LABEL_FALLBACK: Record<string, string> = {
  "compute_provider": "Compute Provider",
  orchestrator: "Orchestrator",
  "contract_host": "Contract Host",
  "payment_provider": "Payment Provider",
};

type RoleOption = {
  id: string;
  label: string;
  description?: string;
};

export function JoinForm({
  orgDid,
  submitting,
  onSubmit,
  knownOrgs,
  onCancel,
  renewal = false,
}: {
  orgDid?: string;
  knownOrgs?: Record<string, any>;
  submitting?: boolean;
  onSubmit: (data: JoinSubmitPayload) => void;
  onCancel?: () => void;
  renewal?: boolean;
}) {
  const [formData, setFormData] = useState<Record<string, string>>({
    name: "",
    why_join: DEFAULT_ROLE,
  });

  if (!orgDid || !knownOrgs?.[orgDid]) {
    return null;
  }

  const org = knownOrgs[orgDid];
  const tokenomics = org?.tokenomics ?? null;
  const requiresWallet = Boolean(tokenomics?.enabled);
  const tokenomicsChain = typeof tokenomics?.chain === "string" ? tokenomics.chain : null;
  const requiredWalletType: WalletType | null =
    requiresWallet && tokenomicsChain === "cardano"
      ? "cardano"
      : requiresWallet && tokenomicsChain === "ethereum"
        ? "ethereum"
        : null;
  const walletConnection = useWalletStore((state) =>
    requiredWalletType ? state.connections[requiredWalletType] : undefined
  );
  const connectedAddress = walletConnection?.address ?? "";
  const walletDisplayName =
    requiredWalletType === "cardano"
      ? "Cardano (Eternl)"
      : requiredWalletType === "ethereum"
        ? "Ethereum (MetaMask)"
        : null;
  const shortWalletAddress = useMemo(() => {
    if (!connectedAddress) return "";
    if (connectedAddress.length <= 18) {
      return connectedAddress;
    }
    return `${connectedAddress.slice(0, 12)}…${connectedAddress.slice(-6)}`;
  }, [connectedAddress]);
  const fields = org.join_fields ?? [];
  const roleOptions = useMemo<RoleOption[]>(() => {
    const rawRoles = Array.isArray(org.roles) ? org.roles : [];
    const seen = new Set<string>();
    const options: RoleOption[] = [];

    rawRoles.forEach((role: any) => {
      let id: string | null = null;
      let label: string | undefined;
      let description: string | undefined;

      if (typeof role === "string") {
        id = role.trim();
      } else if (role && typeof role === "object") {
        const candidates = [role.id, role.value, role.role, role.name];
        for (const candidate of candidates) {
          if (typeof candidate === "string" && candidate.trim()) {
            id = candidate.trim();
            break;
          }
        }
        if (typeof role.label === "string" && role.label.trim()) {
          label = role.label.trim();
        }
        if (typeof role.description === "string" && role.description.trim()) {
          description = role.description.trim();
        }
      }

      if (!id || seen.has(id)) {
        return;
      }

      seen.add(id);
      options.push({
        id,
        label: label ?? ROLE_LABEL_FALLBACK[id] ?? id.replace(/-/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()),
        description,
      });
    });

    if (options.length === 0) {
      options.push({
        id: DEFAULT_ROLE,
        label: ROLE_LABEL_FALLBACK[DEFAULT_ROLE],
      });
    }

    return options;
  }, [org.roles]);
  const supportedRoles = useMemo(() => roleOptions.map((role) => role.id), [roleOptions]);

  useEffect(() => {
    setFormData((prev) => {
      if (supportedRoles.includes(prev["why_join"])) {
        return prev;
      }
      const fallback = supportedRoles[0] ?? DEFAULT_ROLE;
      if (prev["why_join"] === fallback) {
        return prev;
      }
      return {
        ...prev,
        why_join: fallback,
      };
    });
  }, [orgDid, supportedRoles]);

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  // required fields check
  const canSubmit =
    Boolean(formData["name"]?.trim()) &&
    fields.every((f: any) => !f.required || formData[f.name]?.trim()) &&
    (!requiresWallet || Boolean(connectedAddress));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Join {org.name}</CardTitle>
          {requiresWallet && (
            <Badge
              variant="outline"
              className="border-amber-400 bg-amber-50 text-amber-700 dark:border-amber-400/60 dark:bg-amber-500/10 dark:text-amber-200"
            >
              Wallet required
            </Badge>
          )}
          {renewal && (
            <Badge
              variant="secondary"
              className="bg-sky-100 text-sky-800 border-sky-200 dark:bg-sky-500/10 dark:text-sky-100"
            >
              Renewal
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {requiresWallet && (
          <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-400/50 dark:bg-amber-500/10">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-medium">
                  {walletDisplayName ?? "Wallet connection required"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Connect this wallet before sending the join request.
                </p>
              </div>
              {requiredWalletType ? (
                <ConnectWalletButton allowed={[requiredWalletType]} />
              ) : (
                <span className="text-xs text-red-600">
                  Wallet chain is not configured for this organization.
                </span>
              )}
            </div>
            {connectedAddress ? (
              <code
                className="block w-full rounded bg-white px-3 py-2 text-xs font-mono shadow-sm dark:bg-background/50"
                title={connectedAddress}
              >
                {shortWalletAddress}
              </code>
            ) : (
              <p className="text-xs text-muted-foreground">
                No wallet connected yet.
              </p>
            )}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* Always include name */}
          <Input
            value={formData["name"] ?? ""}
            onChange={(e) => handleChange("name", e.target.value)}
            placeholder="Full name"
            data-testid="join-name-input"
          />

          {/* Dynamically render org fields */}
          {fields.map((field: any) => (
            <Input
              key={field.name}
              autoComplete="on"
              type={field.type}
              required={field.required}
              value={formData[field.name] ?? ""}
              onChange={(e) => handleChange(field.name, e.target.value)}
              placeholder={field.label}
              data-testid={`join-field-${field.name}`}
              className={field.type === "text" ? "md:col-span-2" : ""}
            />
          ))}
        </div>

        {/* Roles - radio group */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Roles</Label>
          <RadioGroup
            value={formData["why_join"]}
            onValueChange={(v) => handleChange("why_join", v)}
            className="grid grid-cols-1 md:grid-cols-3 gap-2"
            data-testid="join-role-group"
          >
            {roleOptions.map((role) => (
              <div className="flex items-center space-x-2" key={role.id}>
                <RadioGroupItem
                  value={role.id}
                  id={role.id}
                  data-testid={`join-role-${role.id}`}
                  data-role-id={role.id}
                />
                {role.description ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Label
                        htmlFor={role.id}
                        className="text-sm leading-tight cursor-help"
                      >
                        {role.label}
                      </Label>
                    </TooltipTrigger>
                    <TooltipContent>{role.description}</TooltipContent>
                  </Tooltip>
                ) : (
                  <Label htmlFor={role.id} className="text-sm leading-tight">
                    {role.label}
                  </Label>
                )}
              </div>
            ))}
          </RadioGroup>
        </div>
      </CardContent>
      <CardFooter className="flex flex-col gap-2">
        {requiresWallet && !connectedAddress && (
          <p className="w-full text-xs text-muted-foreground">
            Connect the required wallet above to enable submission.
          </p>
        )}
        <Button
          className="w-full"
          disabled={!canSubmit || submitting}
          onClick={() => {
            const basePayload: Record<string, string> = { ...formData };
            // Ensure all dynamic fields exist in payload
            fields.forEach((field: any) => {
              if (!(field.name in basePayload)) {
                basePayload[field.name] = "";
              }
            });

            const selectedRole =
              supportedRoles.find((role) => role === basePayload["why_join"]) ??
              supportedRoles[0] ??
              DEFAULT_ROLE;

            const payload: JoinSubmitPayload = {
              ...basePayload,
              roles: selectedRole ? [selectedRole] : [],
              wormhole: "",
            };
            if (requiredWalletType && connectedAddress) {
              payload.wallet_address = connectedAddress;
              payload.wallet_chain = requiredWalletType;
            }
            payload.renewal = Boolean(renewal);

            onSubmit(payload);
          }}
          data-testid="join-submit-button"
        >
          {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          {renewal ? "Submit Renewal" : "Submit"}
        </Button>

        <Button
          className="w-full"
          variant={"outline"}
          disabled={submitting}
          onClick={() => onCancel?.()}
          data-testid="join-cancel-button"
        >
          Cancel
        </Button>
      </CardFooter>
    </Card>
  );
}
