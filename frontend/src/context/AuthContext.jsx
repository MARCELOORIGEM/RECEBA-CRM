import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api, apiError, onSessionExpired } from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null = verificando, false = deslogado
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const { data } = await api.get("/auth/me");
        if (vivo) setUser(data);
      } catch {
        if (vivo) setUser(false);
      } finally {
        if (vivo) setLoading(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  // Quando o refresh automático falha, a sessão acabou de verdade: avisa e
  // derruba, em vez de deixar a tela quebrando pedido a pedido.
  useEffect(
    () =>
      onSessionExpired(() => {
        setUser(false);
        toast.error("Sua sessão expirou. Entre novamente.");
      }),
    [],
  );

  const login = useCallback(async (email, password) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      setUser(data);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: apiError(e, "Não foi possível entrar.") };
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* a sessão pode já ter caído; segue o fluxo */
    }
    setUser(false);
  }, []);

  const value = useMemo(
    () => ({ user, setUser, loading, login, logout, isAdmin: user?.role === "admin" }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);
