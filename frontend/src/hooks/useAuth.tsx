import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  AuthResponse,
  getAuthStatus,
  login as requestLogin,
  setupAdminPassword,
} from "../api/auth";
import { setAuthToken, setUnauthorizedHandler } from "../api/api";

interface AuthContextValue {
  loading: boolean;
  passwordSet: boolean;
  token: string | null;
  username: string;
  expiresAt: number | null;
  login: (password: string) => Promise<void>;
  setupPassword: (password: string) => Promise<void>;
  logout: () => void;
  refreshStatus: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const TOKEN_KEY = "nunet-admin-token";
const EXPIRY_KEY = "nunet-admin-expiry";

function persistToken(token: string, expiresAt: number) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRY_KEY, String(expiresAt));
}

function clearPersistedToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRY_KEY);
}

function calculateExpiryTimestamp(seconds: number) {
  return Date.now() + seconds * 1000;
}

function applyTokenState(
  response: AuthResponse,
  setter: (token: string) => void,
  expirySetter: (expiresAt: number) => void
) {
  const expiresAt = calculateExpiryTimestamp(response.expires_in);
  setter(response.access_token);
  expirySetter(expiresAt);
  setAuthToken(response.access_token);
  persistToken(response.access_token, expiresAt);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [passwordSet, setPasswordSet] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [username, setUsername] = useState("admin");

  const logout = useCallback(() => {
    setAuthToken(null);
    setToken(null);
    setExpiresAt(null);
    clearPersistedToken();
  }, []);

  const refreshStatus = useCallback(async () => {
    const status = await getAuthStatus();
    setPasswordSet(status.password_set);
    setUsername(status.username);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => logout());
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const storedExpiry = localStorage.getItem(EXPIRY_KEY);
    if (storedToken && storedExpiry) {
      const parsedExpiry = Number.parseInt(storedExpiry, 10);
      if (!Number.isNaN(parsedExpiry) && parsedExpiry > Date.now()) {
        setToken(storedToken);
        setExpiresAt(parsedExpiry);
        setAuthToken(storedToken);
      } else {
        logout();
      }
    }

    let active = true;
    (async () => {
      try {
        const status = await getAuthStatus();
        if (!active) {
          return;
        }
        setPasswordSet(status.password_set);
        setUsername(status.username);
      } catch (error) {
        console.error("Failed to gather auth status", error);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [logout]);

  useEffect(() => {
    if (!token || !expiresAt) {
      return;
    }
    const delta = expiresAt - Date.now();
    if (delta <= 0) {
      logout();
      return;
    }
    const id = window.setTimeout(() => logout(), delta);
    return () => window.clearTimeout(id);
  }, [token, expiresAt, logout]);

  const login = useCallback(
    async (password: string) => {
      const response = await requestLogin(password);
      applyTokenState(response, (value) => setToken(value), setExpiresAt);
      setPasswordSet(true);
      setUsername(response.username);
    },
    []
  );

  const setupPassword = useCallback(
    async (password: string) => {
      const response = await setupAdminPassword(password);
      applyTokenState(response, (value) => setToken(value), setExpiresAt);
      setPasswordSet(true);
      setUsername(response.username);
    },
    []
  );

  const contextValue = useMemo<AuthContextValue>(
    () => ({
      loading,
      passwordSet,
      token,
      username,
      expiresAt,
      login,
      setupPassword,
      logout,
      refreshStatus,
    }),
    [loading, passwordSet, token, username, expiresAt, login, setupPassword, logout, refreshStatus]
  );

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
