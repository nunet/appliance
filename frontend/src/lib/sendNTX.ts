import { ethers } from "ethers";

const ERC20_ABI = [
  "function transfer(address to, uint256 amount) public returns (bool)",
];

export async function sendNTX(opts: {
  tokenAddress: string;
  to: string;
  amountHuman: string; // e.g., "25"
  decimals: number; // e.g., 6
  chainIdWanted: number; // e.g., 80002
}) {
  const { tokenAddress, to, amountHuman, decimals, chainIdWanted } = opts;

  if (!window.ethereum) {
    throw new Error("MetaMask is not installed");
  }

  // connect and get signer
  await window.ethereum.request({ method: "eth_requestAccounts" });
  const provider = new ethers.BrowserProvider(window.ethereum);
  const signer = await provider.getSigner();

  // ensure correct network
  const net = await provider.getNetwork();
  const current = Number(net.chainId);
  if (current !== chainIdWanted) {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0x" + chainIdWanted.toString(16) }],
    });
  }

  // encode and send
  const token = new ethers.Contract(tokenAddress, ERC20_ABI, signer);
  const amount = ethers.parseUnits(amountHuman, decimals);

  const tx = await token.transfer(to, amount);
  // return immediately with hash so UI can show link
  const receipt = await tx.wait();
  return { hash: tx.hash, receipt };
}
