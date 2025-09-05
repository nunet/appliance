import { ethers } from "ethers";

const ERC20_ABI = [
  "function transfer(address to, uint256 amount) public returns (bool)",
];

function isZeroAddress(addr?: string | null) {
  if (!addr) return true;
  return /^0x0{40}$/i.test(addr.trim());
}

/**
 * Sends NTX or native ETH depending on tokenAddress:
 * - If tokenAddress is 0x000...000 => native transfer (value only)
 * - Else => ERC-20 transfer(to, amount)
 */
export async function sendNTX(opts: {
  tokenAddress: string;
  to: string;
  amountHuman: string;
  decimals: number;
  chainIdWanted: number;
}) {
  const { tokenAddress, to, amountHuman, decimals, chainIdWanted } = opts;

  if (!(window as any).ethereum) {
    throw new Error("MetaMask is not installed");
  }

  // 1) Ensure account access
  await (window as any).ethereum.request({ method: "eth_requestAccounts" });

  // 2) Provider + signer
  let provider = new ethers.BrowserProvider((window as any).ethereum);
  let signer = await provider.getSigner();

  // 3) Ensure correct network; re-create signer after a switch
  const net = await provider.getNetwork();
  if (Number(net.chainId) !== chainIdWanted) {
    await (window as any).ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0x" + chainIdWanted.toString(16) }],
    });

    // re-bind after switch
    provider = new ethers.BrowserProvider((window as any).ethereum);
    signer = await provider.getSigner();
  }

  // 4) Build and send the transaction
  const parsed = ethers.parseUnits(amountHuman, decimals);

  // Native ETH path
  if (isZeroAddress(tokenAddress)) {
    const tx = await signer.sendTransaction({
      to,
      value: parsed,
    });
    const receipt = await tx.wait();
    return { hash: tx.hash, receipt };
  }

  // ERC-20 path
  const token = new ethers.Contract(tokenAddress, ERC20_ABI, signer);
  const tx = await token.transfer(to, parsed);
  const receipt = await tx.wait();
  return { hash: tx.hash, receipt };
}
