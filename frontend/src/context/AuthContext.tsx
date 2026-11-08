import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { AuthUser, Role } from '../types';
import { api, setApiToken, setUnauthorizedHandler } from '../utils/api';

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  sessionExpired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

const TOKEN_KEY = 'loyalty_auth_token';
const USER_KEY = 'loyalty_user';
const AuthContext = createContext<AuthContextType | undefined>(undefined);

const readUser = (): AuthUser | null => {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Токен хранится только на время сеанса браузера (sessionStorage) и передается в заголовке Authorization
  const [user, setUser] = useState<AuthUser | null>(() => {
    const token = sessionStorage.getItem(TOKEN_KEY);
    setApiToken(token);
    return token ? readUser() : null;
  });
  const [sessionExpired, setSessionExpired] = useState(false);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    setApiToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSessionExpired(true);
      logout();
    });
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = async (username: string, password: string) => {
    const data = await api.post<{ access_token: string; user_id: number; username: string; role: Role }>(
      '/api/v1/auth/login', { username, password });
    const authUser: AuthUser = { id: data.user_id, username: data.username, role: data.role };
    sessionStorage.setItem(TOKEN_KEY, data.access_token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(authUser));
    setApiToken(data.access_token);
    setSessionExpired(false);
    setUser(authUser);
  };

  const hasRole = (...roles: Role[]) => !!user && roles.includes(user.role);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, sessionExpired, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth должен использоваться внутри AuthProvider');
  return context;
};
