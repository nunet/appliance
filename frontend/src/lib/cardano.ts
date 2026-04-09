import { bech32 } from "@scure/base";

import type { WalletConnection } from "@/stores/walletStore";

export interface Cip30Api {
  getNetworkId?: () => Promise<number>;
  getUsedAddresses?: () => Promise<string[]>;
  getChangeAddress?: () => Promise<string>;
  getRewardAddresses?: () => Promise<string[]>;
}

export interface EternlNamespace {
  name?: string;
  icon?: string;
  isEnabled?: () => Promise<boolean>;
  enable: () => Promise<Cip30Api>;
}

export function isCardanoWalletAvailable(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return Boolean((window as unknown as { cardano?: { eternl?: EternlNamespace } }).cardano?.eternl);
}

export function getEternlNamespace(): EternlNamespace | null {
  if (typeof window === "undefined") {
    return null;
  }
  const cardano = (window as unknown as { cardano?: { eternl?: EternlNamespace } }).cardano;
  return cardano?.eternl ?? null;
}

function hexToBytes(hex: string): Uint8Array {
  const normalized = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (normalized.length % 2 !== 0) {
    throw new Error("Invalid hex string");
  }
  const array = new Uint8Array(normalized.length / 2);
  for (let i = 0; i < normalized.length; i += 2) {
    array[i / 2] = parseInt(normalized.slice(i, i + 2), 16);
  }
  return array;
}

function bech32Prefix(bytes: Uint8Array): string {
  const header = bytes[0];
  const type = header >> 4;
  const networkId = header & 0xf;
  const isStake = type === 14 || type === 15;
  const basePrefix = isStake ? "stake" : "addr";
  return networkId === 1 ? basePrefix : `${basePrefix}_test`;
}

export function hexAddressToBech32(addressHex: string): string {
  const bytes = hexToBytes(addressHex);
  const prefix = bech32Prefix(bytes);
  const words = bech32.toWords(bytes);
  return bech32.encode(prefix, words, 1000);
}

export async function resolveEternlAddress(api: Cip30Api): Promise<string> {
  const used = (await api.getUsedAddresses?.()) ?? [];
  const reward = (await api.getRewardAddresses?.()) ?? [];
  const change = api.getChangeAddress ? await api.getChangeAddress() : undefined;

  const candidate = used[0] ?? reward[0] ?? change;
  if (!candidate) {
    throw new Error("Eternl wallet did not return any address");
  }
  return hexAddressToBech32(candidate);
}

export async function buildCardanoConnection(api: Cip30Api): Promise<WalletConnection> {
  const address = await resolveEternlAddress(api);
  const networkId = api.getNetworkId ? await api.getNetworkId() : undefined;
  const changeHex = api.getChangeAddress ? await api.getChangeAddress() : null;
  const changeAddress = changeHex ? hexAddressToBech32(changeHex) : address;
  return {
    address,
    changeAddress,
    label: networkId === 1 ? "Cardano Mainnet" : "Cardano Testnet",
    provider: "Eternl",
    networkId,
    cardanoApi: api,
  };
}
