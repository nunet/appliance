import { Wallet } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/button";
import { useWallet } from "./useWallet";

function shorten(addr: string) {
  return addr.slice(0, 6) + "…" + addr.slice(-4);
}

export function ConnectWalletButton() {
  const { address, isConnecting, connect } = useWallet();

  async function onClick() {
    try {
      await connect();
    } catch (e: any) {
      toast.error("MetaMask not found or rejected", {
        description: e?.message,
      });
    }
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      className="font-mono"
      disabled={isConnecting}
      title={address ? "Connected" : "Connect wallet"}
    >
      <Wallet className="h-4 w-4 mr-2" />
      {address ? shorten(address) : isConnecting ? "Connecting…" : "Connect"}
    </Button>
  );
}
