import { api } from "./api";

export interface AuthStatus {
  password_set: boolean;
  username: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  username: string;
}

export const getAuthStatus = async () => {
  const res = await api.get<AuthStatus>("/auth/status");
  return res.data;
};

export const setupAdminPassword = async (password: string) => {
  const res = await api.post<AuthResponse>("/auth/setup", { password });
  return res.data;
};

export const login = async (password: string) => {
  const res = await api.post<AuthResponse>("/auth/token", { password });
  return res.data;
};
