import { create } from "zustand";
import type { Cip30Api } from "@/lib/cardano";

export type WalletType = "ethereum" | "cardano";

export interface WalletConnection {
  address: string;
  changeAddress?: string;
  label: string;
  provider: string;
  networkId?: number;
  cardanoApi?: Cip30Api;
}

interface WalletState {
  active: WalletType | null;
  connections: Partial<Record<WalletType, WalletConnection>>;
  activate: (type: WalletType) => void;
  setConnection: (type: WalletType, connection: WalletConnection | null) => void;
  clear: () => void;
}

const walletOrder: WalletType[] = ["ethereum", "cardano"];

export const useWalletStore = create<WalletState>((set) => ({
  active: null,
  connections: {},
  activate: (type) =>
    set((state) => {
      if (!state.connections[type]) {
        return state;
      }
      return { active: type };
    }),
  setConnection: (type, connection) =>
    set((state) => {
      const nextConnections: Partial<Record<WalletType, WalletConnection>> = {
        ...state.connections,
      };
      let nextActive = state.active;

      if (!connection) {
        delete nextConnections[type];
        if (state.active === type) {
          const remaining = walletOrder.filter((key) => Boolean(nextConnections[key]));
          nextActive = remaining.length ? remaining[0] : null;
        }
        return {
          active: nextActive,
          connections: nextConnections,
        };
      }

      nextConnections[type] = connection;
      if (!state.active) {
        nextActive = type;
      }

      return {
        active: nextActive,
        connections: nextConnections,
      };
    }),
  clear: () => set({ active: null, connections: {} }),
}));
