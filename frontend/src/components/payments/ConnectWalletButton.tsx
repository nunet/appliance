import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Loader2, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { useWalletStore, type WalletType } from "@/stores/walletStore";
import {
  buildCardanoConnection,
  getEternlNamespace,
  isCardanoWalletAvailable,
} from "@/lib/cardano";

function middleEllipsis(value: string, head = 6, tail = 4) {
  if (!value) return "";
  if (value.length <= head + tail + 3) {
    return value;
  }
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function ethereumLabel(chainId?: number) {
  switch (chainId) {
    case 1:
      return "Ethereum Mainnet";
    case 5:
      return "Ethereum Goerli";
    case 10:
      return "OP Mainnet";
    case 137:
      return "Polygon";
    case 42161:
      return "Arbitrum One";
    case 11155111:
      return "Ethereum Sepolia";
    default:
      return "Ethereum";
  }
}

export function ConnectWalletButton() {
  const [busy, setBusy] = useState<WalletType | null>(null);
  const [isCardanoReady, setIsCardanoReady] = useState<boolean>(() =>
    typeof window !== "undefined" ? isCardanoWalletAvailable() : false,
  );

  const activeType = useWalletStore((state) => state.active);
  const connections = useWalletStore((state) => state.connections);
  const setConnection = useWalletStore((state) => state.setConnection);
  const activate = useWalletStore((state) => state.activate);

  const activeConnection = activeType ? connections[activeType] : undefined;

  const buttonLabel = useMemo(() => {
    if (!activeConnection) {
      return "Connect wallet";
    }
    return `${activeConnection.provider}: ${middleEllipsis(activeConnection.address, 6, 6)}`;
  }, [activeConnection]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const updateCardanoReady = () => setIsCardanoReady(isCardanoWalletAvailable());
    updateCardanoReady();

    window.addEventListener?.("cardano#initialized", updateCardanoReady);

    const timer = window.setTimeout(updateCardanoReady, 1500);

    return () => {
      window.removeEventListener?.("cardano#initialized", updateCardanoReady);
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    const eth = (window as unknown as { ethereum?: any }).ethereum;
    if (!eth?.request) {
      return;
    }

    let canceled = false;

    const applyAccount = async (accounts: string[]) => {
      if (canceled) return;
      const account = accounts?.[0];
      if (!account) {
        setConnection("ethereum", null);
        return;
      }
      let chainId: number | undefined;
      try {
        const chainHex = await eth.request({ method: "eth_chainId" });
        if (typeof chainHex === "string") {
          chainId = Number.parseInt(chainHex, 16);
        }
      } catch (err) {
        console.warn("Failed to obtain chainId", err);
      }

      if (!canceled) {
        setConnection("ethereum", {
          address: account,
          label: ethereumLabel(chainId),
          provider: "MetaMask",
          networkId: chainId,
        });
      }
    };

    eth
      .request({ method: "eth_accounts" })
      .then((accounts: string[]) => applyAccount(accounts))
      .catch(() => undefined);

    const handleAccountsChanged = (accounts: string[]) => {
      applyAccount(accounts).catch((err) => console.error(err));
    };

    eth.on?.("accountsChanged", handleAccountsChanged);

    return () => {
      canceled = true;
      eth.removeListener?.("accountsChanged", handleAccountsChanged);
    };
  }, [setConnection]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const namespace = getEternlNamespace();
    if (!namespace?.isEnabled) {
      return;
    }
    let canceled = false;

    namespace
      .isEnabled()
      .then((enabled) => (enabled ? namespace.enable() : null))
      .then(async (api) => {
        if (!api || canceled) return;
        try {
          const connection = await buildCardanoConnection(api);
          if (!canceled) {
            setConnection("cardano", connection);
          }
        } catch (err) {
          console.warn("Failed to restore Eternl session", err);
        }
      })
      .catch((err) => {
        console.warn("Eternl auto connect failed", err);
      });

    return () => {
      canceled = true;
    };
  }, [setConnection]);

  const handleActivate = (type: WalletType) => {
    const connection = connections[type];
    if (!connection) {
      return;
    }
    activate(type);
    toast.success(`${connection.provider} selected`, {
      description: middleEllipsis(connection.address, 8, 6),
    });
  };

  const connectEthereum = async () => {
    const eth = (window as unknown as { ethereum?: any }).ethereum;
    if (!eth?.request) {
      toast.error("MetaMask not found");
      return;
    }

    try {
      setBusy("ethereum");
      const accounts: string[] = await eth.request({ method: "eth_requestAccounts" });
      if (!accounts?.length) {
        toast.error("MetaMask did not return any accounts");
        setConnection("ethereum", null);
        return;
      }
      const account = accounts[0];
      let chainId: number | undefined;
      try {
        const chainHex = await eth.request({ method: "eth_chainId" });
        if (typeof chainHex === "string") {
          chainId = Number.parseInt(chainHex, 16);
        }
      } catch (err) {
        console.warn("Failed to obtain chainId", err);
      }

      setConnection("ethereum", {
        address: account,
        label: ethereumLabel(chainId),
        provider: "MetaMask",
        networkId: chainId,
      });
      activate("ethereum");
      toast.success("Connected to MetaMask", {
        description: middleEllipsis(account, 10, 6),
      });
    } catch (error: any) {
      const message = error?.message ?? "Connection rejected";
      toast.error("MetaMask connection failed", { description: message });
    } finally {
      setBusy(null);
    }
  };

  const connectCardano = async () => {
    const namespace = getEternlNamespace();
    if (!namespace) {
      toast.error("Eternl wallet not found");
      return;
    }

    try {
      setBusy("cardano");
      const api = await namespace.enable();
      const connection = await buildCardanoConnection(api);
      setConnection("cardano", connection);
      activate("cardano");
      toast.success("Connected to Eternl", {
        description: middleEllipsis(connection.address, 10, 6),
      });
    } catch (error: any) {
      const message = error?.info ?? error?.message ?? "Connection rejected";
      toast.error("Eternl connection failed", { description: message });
    } finally {
      setBusy(null);
    }
  };

  const disconnect = (type: WalletType) => {
    const connection = connections[type];
    if (!connection) {
      return;
    }
    setConnection(type, null);
    toast.info(`${connection.provider} disconnected`);
  };

  const walletItems: Array<{
    type: WalletType;
    title: string;
    description: string;
    connected: boolean;
    address?: string;
    isActive: boolean;
    onConnect: () => void;
    onDisconnect: () => void;
    onActivate: () => void;
    disabled?: boolean;
  }> = [
    {
      type: "ethereum",
      title: "MetaMask",
      description: connections.ethereum?.label ?? "Ethereum wallet",
      connected: Boolean(connections.ethereum),
      address: connections.ethereum?.address,
      isActive: activeType === "ethereum",
      onConnect: connectEthereum,
      onDisconnect: () => disconnect("ethereum"),
      onActivate: () => handleActivate("ethereum"),
    },
    {
      type: "cardano",
      title: "Eternl",
      description: connections.cardano?.label ?? "Cardano wallet",
      connected: Boolean(connections.cardano),
      address: connections.cardano?.address,
      isActive: activeType === "cardano",
      onConnect: connectCardano,
      onDisconnect: () => disconnect("cardano"),
      onActivate: () => handleActivate("cardano"),
      disabled: !isCardanoReady,
    },
  ];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          type="button"
          className="font-mono"
          title={activeConnection?.address ?? "Connect wallet"}
        >
          <Wallet className="mr-2 h-4 w-4" />
          {buttonLabel}
          <ChevronDown className="ml-1 h-3.5 w-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 space-y-2">
        <DropdownMenuLabel>Select a wallet</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {walletItems.map((item) => (
          <div
            key={item.type}
            className="flex flex-col gap-2 rounded-md border border-border/60 p-3"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">{item.title}</p>
                <p className="text-xs text-muted-foreground">{item.description}</p>
              </div>
              <span
                className={
                  item.connected
                    ? "text-xs font-medium text-emerald-500"
                    : "text-xs text-muted-foreground"
                }
              >
                {item.connected ? (item.isActive ? "Active" : "Connected") : "Idle"}
              </span>
            </div>
            {item.address && (
              <code className="rounded bg-muted px-2 py-1 text-xs">
                {middleEllipsis(item.address, 12, 8)}
              </code>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              {item.connected && (
                <Button
                  variant={item.isActive ? "secondary" : "outline"}
                  size="xs"
                  type="button"
                  onClick={item.onActivate}
                >
                  {item.isActive ? "In use" : "Use"}
                </Button>
              )}
              <Button
                variant="ghost"
                size="xs"
                type="button"
                onClick={item.connected ? item.onDisconnect : item.onConnect}
                disabled={
                  item.disabled ||
                  (busy !== null && busy !== item.type) ||
                  (item.disabled && !item.connected)
                }
              >
                {busy === item.type ? (
                  <>
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    Working
                  </>
                ) : item.connected ? (
                  "Disconnect"
                ) : item.disabled ? (
                  "Unavailable"
                ) : (
                  "Connect"
                )}
              </Button>
            </div>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
