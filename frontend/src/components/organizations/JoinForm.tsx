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
const BLOCKCHAIN_LABELS: Record<WalletType, string> = {
  ethereum: "Ethereum",
  cardano: "Cardano",
};
const BLOCKCHAIN_WALLET_HINT: Record<WalletType, string> = {
  ethereum: "MetaMask",
  cardano: "Eternl",
};

type RoleOption = {
  id: string;
  label: string;
  description?: string;
};

type JoinField = {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
};

type RoleConfig =
  | string
  | {
      id?: string;
      value?: string;
      role?: string;
      name?: string;
      label?: string;
      description?: string;
    };

type KnownOrg = {
  name?: string;
  tokenomics?: {
    enabled?: boolean;
    chain?: string;
    blockchains?: string[];
  };
  blockchains?: string[];
  blockchain?: string;
  join_fields?: JoinField[];
  roles?: RoleConfig[];
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
  knownOrgs?: Record<string, KnownOrg>;
  submitting?: boolean;
  onSubmit: (data: JoinSubmitPayload) => void;
  onCancel?: () => void;
  renewal?: boolean;
}) {
  const [formData, setFormData] = useState<Record<string, string>>({
    name: "",
    why_join: DEFAULT_ROLE,
  });

  const org = orgDid ? knownOrgs?.[orgDid] : null;
  const tokenomics = org?.tokenomics ?? null;
  const requiresWallet = Boolean(tokenomics?.enabled);
  const tokenomicsChains = useMemo<WalletType[]>(() => {
    const candidates: string[] = [];
    if (Array.isArray(org?.blockchains)) {
      for (const chain of org.blockchains) {
        if (typeof chain === "string" && chain.trim()) {
          candidates.push(chain.trim().toLowerCase());
        }
      }
    }
    if (typeof org?.blockchain === "string" && org.blockchain.trim()) {
      candidates.push(org.blockchain.trim().toLowerCase());
    }
    if (Array.isArray(tokenomics?.blockchains)) {
      for (const chain of tokenomics.blockchains) {
        if (typeof chain === "string" && chain.trim()) {
          candidates.push(chain.trim().toLowerCase());
        }
      }
    }
    if (typeof tokenomics?.chain === "string" && tokenomics.chain.trim()) {
      candidates.push(tokenomics.chain.trim().toLowerCase());
    }

    const seen = new Set<WalletType>();
    const normalized: WalletType[] = [];
    candidates.forEach((chain) => {
      if (chain === "ethereum" || chain === "cardano") {
        if (!seen.has(chain)) {
          seen.add(chain);
          normalized.push(chain);
        }
      }
    });
    return normalized;
  }, [org?.blockchain, org?.blockchains, tokenomics]);
  const blockchainOptions = useMemo(
    () =>
      tokenomicsChains.map((chain) => ({
        id: chain,
        label: BLOCKCHAIN_LABELS[chain],
        walletHint: BLOCKCHAIN_WALLET_HINT[chain],
      })),
    [tokenomicsChains]
  );
  const selectedBlockchainRaw = typeof formData["blockchain"] === "string" ? formData["blockchain"].trim().toLowerCase() : "";
  const selectedBlockchain: WalletType | null =
    selectedBlockchainRaw === "ethereum" || selectedBlockchainRaw === "cardano"
      ? selectedBlockchainRaw
      : null;
  const requiredWalletType: WalletType | null = requiresWallet ? selectedBlockchain : null;
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
  const fields: JoinField[] = org?.join_fields ?? [];
  const roleOptions = useMemo<RoleOption[]>(() => {
    const rawRoles: RoleConfig[] = Array.isArray(org?.roles) ? org.roles : [];
    const seen = new Set<string>();
    const options: RoleOption[] = [];

    rawRoles.forEach((role) => {
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
  }, [org?.roles]);
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
  useEffect(() => {
    setFormData((prev) => {
      const current = typeof prev["blockchain"] === "string" ? prev["blockchain"].trim().toLowerCase() : "";
      const exists = blockchainOptions.some((option) => option.id === current);
      if (exists) {
        if (prev["blockchain"] === current) {
          return prev;
        }
        return { ...prev, blockchain: current };
      }
      const fallback = blockchainOptions.length === 1 ? blockchainOptions[0].id : "";
      if ((prev["blockchain"] ?? "") === fallback) {
        return prev;
      }
      return {
        ...prev,
        blockchain: fallback,
      };
    });
  }, [orgDid, blockchainOptions]);

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  // required fields check
  const canSubmit =
    Boolean(formData["name"]?.trim()) &&
    fields.every((f) => !f.required || formData[f.name]?.trim()) &&
    (blockchainOptions.length === 0 || Boolean(selectedBlockchain)) &&
    (!requiresWallet || Boolean(connectedAddress));

  if (!orgDid || !org) {
    return null;
  }

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
        {blockchainOptions.length > 0 && (
          <div className="space-y-2">
            <Label className="text-sm font-medium">Blockchain</Label>
            <RadioGroup
              value={selectedBlockchain ?? ""}
              onValueChange={(v) => handleChange("blockchain", v)}
              className="grid grid-cols-1 md:grid-cols-2 gap-2"
              data-testid="join-blockchain-group"
            >
              {blockchainOptions.map((option) => (
                <div className="flex items-center space-x-2" key={option.id}>
                  <RadioGroupItem
                    value={option.id}
                    id={`blockchain-${option.id}`}
                    data-testid={`join-blockchain-${option.id}`}
                  />
                  <Label htmlFor={`blockchain-${option.id}`} className="text-sm leading-tight">
                    {option.label} ({option.walletHint})
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        )}
        {requiresWallet && (
          <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-400/50 dark:bg-amber-500/10">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-medium">
                  {walletDisplayName ?? "Wallet connection required"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {selectedBlockchain
                    ? "Connect this wallet before sending the join request."
                    : "Select a blockchain first, then connect the matching wallet."}
                </p>
              </div>
              {requiredWalletType ? (
                <ConnectWalletButton allowed={[requiredWalletType]} />
              ) : (
                <span className="text-xs text-red-600">Select a blockchain to enable wallet connection.</span>
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
                {selectedBlockchain ? "No wallet connected yet." : "No blockchain selected yet."}
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
          {fields.map((field) => (
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
            fields.forEach((field) => {
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
            if (selectedBlockchain) {
              payload.blockchain = selectedBlockchain;
            }
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
