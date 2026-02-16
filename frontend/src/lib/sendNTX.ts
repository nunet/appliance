import { ethers } from "ethers";

const ERC20_ABI = [
  "function transfer(address to, uint256 amount) public returns (bool)",
  "function balanceOf(address owner) view returns (uint256)",
  "error ERC20InsufficientBalance(address sender, uint256 balance, uint256 needed)",
  "error ERC20InvalidSender(address sender)",
  "error ERC20InvalidReceiver(address receiver)",
];

const INSUFFICIENT_BALANCE_SELECTOR = "0xe450d38c";
const ERC20_INTERFACE = new ethers.Interface(ERC20_ABI);

function isHexData(value: unknown): value is string {
  return typeof value === "string" && /^0x[0-9a-fA-F]+$/.test(value);
}

function extractErrorData(error: unknown): string | null {
  const seen = new Set<unknown>();
  const queue: unknown[] = [error];

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || seen.has(current)) {
      continue;
    }
    seen.add(current);

    if (isHexData(current) && current.length >= 10) {
      return current;
    }

    if (typeof current === "string") {
      const match = current.match(/0x[0-9a-fA-F]{10,}/);
      if (match?.[0]) {
        return match[0];
      }
      continue;
    }

    if (typeof current !== "object") {
      continue;
    }

    const record = current as Record<string, unknown>;
    if (typeof record.message === "string") {
      const match = record.message.match(/data="?((0x[0-9a-fA-F]{10,}))"?/i) || record.message.match(/0x[0-9a-fA-F]{10,}/);
      if (match?.[1] || match?.[0]) {
        return (match[1] || match[0]) as string;
      }
    }

    queue.push(record.data, record.error, record.info, record.cause, record.body);
  }

  return null;
}

function decodeInsufficientBalanceSelector(dataHex: string, decimals: number): string | null {
  const normalized = dataHex.toLowerCase();
  if (!normalized.startsWith(INSUFFICIENT_BALANCE_SELECTOR)) {
    return null;
  }

  const payload = normalized.slice(10);
  // selector + 3 static ABI words: sender, balance, needed
  if (payload.length < 64 * 3) {
    return null;
  }

  try {
    const senderWord = payload.slice(0, 64);
    const balanceWord = payload.slice(64, 128);
    const neededWord = payload.slice(128, 192);

    const sender = `0x${senderWord.slice(24)}`;
    const balance = BigInt(`0x${balanceWord}`);
    const needed = BigInt(`0x${neededWord}`);

    return `Insufficient token balance for ${sender}: have ${ethers.formatUnits(balance, decimals)}, need ${ethers.formatUnits(needed, decimals)}.`;
  } catch {
    return null;
  }
}

function decodeErc20TransferError(error: unknown, decimals: number): string | null {
  const dataHex = extractErrorData(error);
  if (!dataHex) {
    return null;
  }

  try {
    const parsed = ERC20_INTERFACE.parseError(dataHex);
    if (parsed?.name === "ERC20InsufficientBalance") {
      const sender = String(parsed.args?.[0] ?? "");
      const balance = BigInt(parsed.args?.[1] ?? 0n);
      const needed = BigInt(parsed.args?.[2] ?? 0n);
      return `Insufficient token balance for ${sender}: have ${ethers.formatUnits(balance, decimals)}, need ${ethers.formatUnits(needed, decimals)}.`;
    }
    if (parsed?.name === "ERC20InvalidSender") {
      const sender = String(parsed.args?.[0] ?? "");
      return `Token contract rejected sender address ${sender}.`;
    }
    if (parsed?.name === "ERC20InvalidReceiver") {
      const receiver = String(parsed.args?.[0] ?? "");
      return `Token contract rejected receiver address ${receiver}.`;
    }
  } catch {
    // Fallback to selector-only decoding below.
  }

  return decodeInsufficientBalanceSelector(dataHex, decimals);
}

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

  // connect wallet first
  await window.ethereum.request({ method: "eth_requestAccounts" });
  let provider = new ethers.BrowserProvider(window.ethereum);

  // ensure correct network
  const net = await provider.getNetwork();
  const current = Number(net.chainId);
  if (current !== chainIdWanted) {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0x" + chainIdWanted.toString(16) }],
    });
    provider = new ethers.BrowserProvider(window.ethereum);
  }

  const signer = await provider.getSigner();

  // encode and send
  const token = new ethers.Contract(tokenAddress, ERC20_ABI, signer);
  const signerAddress = await signer.getAddress();
  const amount = ethers.parseUnits(amountHuman, decimals);
  const currentBalance = await token.balanceOf(signerAddress) as bigint;

  if (currentBalance < amount) {
    throw new Error(
      `Insufficient token balance for ${signerAddress}: have ${ethers.formatUnits(currentBalance, decimals)}, need ${amountHuman}.`
    );
  }

  try {
    const tx = await token.transfer(to, amount);
    // return immediately with hash so UI can show link
    const receipt = await tx.wait();
    return { hash: tx.hash, receipt };
  } catch (error: unknown) {
    const friendly = decodeErc20TransferError(error, decimals);
    if (friendly) {
      throw new Error(friendly);
    }
    throw error;
  }
}
