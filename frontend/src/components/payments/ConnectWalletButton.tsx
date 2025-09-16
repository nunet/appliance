import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/button";

function shorten(addr: string) {
  return addr.slice(0, 6) + "…" + addr.slice(-4);
}

export function ConnectWalletButton() {
  const [address, setAddress] = useState<string | null>(null);

  useEffect(() => {
    const eth = (window as any).ethereum;
    if (!eth?.on) return;
    const handleAccountsChanged = (accounts: string[]) =>
      setAddress(accounts?.[0] ?? null);
    eth.on("accountsChanged", handleAccountsChanged);
    return () => {
      eth.removeListener?.("accountsChanged", handleAccountsChanged);
    };
  }, []);

  async function connect() {
    const eth = (window as any).ethereum;
    if (!eth) {
      toast.error("MetaMask not found");
      return;
    }
    try {
      const accounts = await eth.request({ method: "eth_requestAccounts" });
      setAddress(accounts?.[0] ?? null);
    } catch (e: any) {
      toast.error("Connection rejected", { description: e?.message });
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={connect} className="font-mono">
      <Wallet className="h-4 w-4 mr-2" />
      {address ? shorten(address) : "Connect"}
    </Button>
  );
}
