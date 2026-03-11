import { ethers } from "ethers";

const ERC20_ABI = [
  "function transfer(address to, uint256 amount) public returns (bool)",
  "function balanceOf(address owner) view returns (uint256)",
  "function decimals() view returns (uint8)",
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

function parseDecimalAmountToUnitsCeil(amountHuman: string, decimals: number): { units: bigint; rounded: boolean } {
  const raw = amountHuman.trim();
  if (!/^\d+(\.\d+)?$/.test(raw)) {
    throw new Error(`Invalid amount format: ${amountHuman}`);
  }

  const [wholeRaw, fracRaw = ""] = raw.split(".");
  const whole = wholeRaw.replace(/^0+/, "") || "0";
  const base = 10n ** BigInt(decimals);
  const wholeUnits = BigInt(whole) * base;

  if (decimals === 0) {
    const rounded = /[1-9]/.test(fracRaw);
    return { units: wholeUnits + (rounded ? 1n : 0n), rounded };
  }

  const fracPadded = (fracRaw || "").padEnd(decimals, "0");
  const fracTruncated = fracPadded.slice(0, decimals);
  const fracUnits = BigInt(fracTruncated || "0");
  const overflowPart = (fracRaw || "").slice(decimals);
  const rounded = /[1-9]/.test(overflowPart);

  return {
    units: wholeUnits + fracUnits + (rounded ? 1n : 0n),
    rounded,
  };
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
  let onChainDecimals = decimals;
  try {
    const onChainDecimalsRaw = await token.decimals() as bigint | number;
    const parsed = Number(onChainDecimalsRaw);
    if (!Number.isInteger(parsed) || parsed < 0 || parsed > 36) {
      throw new Error(`Invalid token decimals from contract: ${String(onChainDecimalsRaw)}`);
    }
    onChainDecimals = parsed;
  } catch {
    // Fallback to configured decimals if contract does not expose decimals().
    onChainDecimals = decimals;
  }

  if (onChainDecimals !== decimals) {
    console.warn(
      `Token decimals mismatch for ${tokenAddress}: config=${decimals}, onchain=${onChainDecimals}. Using on-chain value.`
    );
  }

  const { units: amount } = parseDecimalAmountToUnitsCeil(amountHuman, onChainDecimals);
  const amountDisplay = ethers.formatUnits(amount, onChainDecimals);
  const currentBalance = await token.balanceOf(signerAddress) as bigint;

  if (currentBalance < amount) {
    throw new Error(
      `Insufficient token balance for ${signerAddress}: have ${ethers.formatUnits(currentBalance, onChainDecimals)}, need ${amountDisplay}.`
    );
  }

  try {
    const tx = await token.transfer(to, amount);
    // return immediately with hash so UI can show link
    const receipt = await tx.wait();
    return { hash: tx.hash, receipt };
  } catch (error: unknown) {
    const friendly = decodeErc20TransferError(error, onChainDecimals);
    if (friendly) {
      throw new Error(friendly);
    }
    throw error;
  }
}
