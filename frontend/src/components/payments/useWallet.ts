import { useEffect, useState, useCallback } from "react";

export function useWallet() {
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);

  useEffect(() => {
    const eth = (window as any).ethereum;
    if (!eth?.request) return;

    // eager restore without prompting
    (async () => {
      try {
        const [accounts, cid] = await Promise.all([
          eth.request({ method: "eth_accounts" }),
          eth.request({ method: "eth_chainId" }).catch(() => null),
        ]);
        setAddress(accounts?.[0] ?? null);
        if (cid) setChainId(cid);
      } catch {
        /* ignore */
      }
    })();

    const handleAccountsChanged = (accounts: string[]) =>
      setAddress(accounts?.[0] ?? null);
    const handleChainChanged = (cid: string) => setChainId(cid);
    const handleDisconnect = () => setAddress(null);

    eth.on?.("accountsChanged", handleAccountsChanged);
    eth.on?.("chainChanged", handleChainChanged);
    eth.on?.("disconnect", handleDisconnect);

    return () => {
      eth.removeListener?.("accountsChanged", handleAccountsChanged);
      eth.removeListener?.("chainChanged", handleChainChanged);
      eth.removeListener?.("disconnect", handleDisconnect);
    };
  }, []);

  const connect = useCallback(async () => {
    const eth = (window as any).ethereum;
    if (!eth?.request) throw new Error("MetaMask not found");
    setIsConnecting(true);
    try {
      const accounts: string[] = await eth.request({
        method: "eth_requestAccounts",
      });
      setAddress(accounts?.[0] ?? null);
      const cid: string = await eth.request({ method: "eth_chainId" });
      setChainId(cid);
      return accounts?.[0] ?? null;
    } finally {
      setIsConnecting(false);
    }
  }, []);

  return { address, chainId, isConnecting, connect, isConnected: !!address };
}
