import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  withCredentials: true,
});

/* ------------------------------------------------------------------ *
 * Renovação de sessão
 *
 * O token de acesso vale 60 minutos. O backend sempre teve /auth/refresh,
 * mas nada no frontend chamava: passada uma hora, toda tela começava a
 * falhar em silêncio até o usuário recarregar a página.
 *
 * Aqui o primeiro 401 dispara um refresh; as demais requisições que
 * falharem enquanto ele acontece entram na fila e são repetidas depois,
 * em vez de dispararem N refreshes em paralelo.
 * ------------------------------------------------------------------ */
let refreshing = null;
let fila = [];
const ouvintesDeSessao = new Set();

export function onSessionExpired(fn) {
  ouvintesDeSessao.add(fn);
  return () => ouvintesDeSessao.delete(fn);
}

const SEM_REFRESH = ["/auth/login", "/auth/refresh", "/auth/me", "/auth/logout"];

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const url = original?.url || "";

    if (status !== 401 || original?._retentado || SEM_REFRESH.some((p) => url.includes(p))) {
      return Promise.reject(error);
    }

    original._retentado = true;
    if (!refreshing) {
      refreshing = api
        .post("/auth/refresh")
        .then((res) => {
          fila.forEach(({ resolve }) => resolve());
          return res;
        })
        .catch((e) => {
          fila.forEach(({ reject }) => reject(e));
          ouvintesDeSessao.forEach((fn) => fn());
          throw e;
        })
        .finally(() => {
          fila = [];
          refreshing = null;
        });
    } else {
      await new Promise((resolve, reject) => fila.push({ resolve, reject }));
      return api(original);
    }

    await refreshing;
    return api(original);
  },
);

/** Mensagem de erro legível a partir de qualquer formato que o backend devolva. */
export function apiError(e, fallback = "Algo deu errado. Tente novamente.") {
  const detail = e?.response?.data?.detail;
  if (detail == null) {
    if (e?.code === "ERR_NETWORK") return "Sem conexão com o servidor.";
    return e?.message || fallback;
  }
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (
      detail
        .map((d) => (typeof d?.msg === "string" ? d.msg : null))
        .filter(Boolean)
        .join(" • ") || fallback
    );
  }
  if (typeof detail?.msg === "string") return detail.msg;
  return fallback;
}

/** GET que aceita tanto a resposta paginada nova quanto um array puro. */
export async function getList(url, params) {
  const { data } = await api.get(url, { params });
  if (Array.isArray(data)) return { items: data, total: data.length, page: 1, pages: 1 };
  return data;
}

/**
 * Percorre todas as páginas de uma listagem.
 *
 * O servidor limita `page_size` a 200. Pedir 200 e usar o resultado como se
 * fosse o conjunto completo faz o relatório truncar em silêncio assim que a
 * operação passar desse volume — e ninguém percebe, porque o total não aparece.
 */
export async function getAll(url, params = {}, { maxPaginas = 50 } = {}) {
  const pageSize = 200;
  const primeira = await getList(url, { ...params, page: 1, page_size: pageSize });
  const paginas = Math.min(primeira.pages || 1, maxPaginas);
  if (paginas <= 1) return primeira;

  const restantes = await Promise.all(
    Array.from({ length: paginas - 1 }, (_, i) =>
      getList(url, { ...params, page: i + 2, page_size: pageSize }),
    ),
  );
  const items = restantes.reduce((acc, p) => acc.concat(p.items || []), [...primeira.items]);
  return {
    ...primeira,
    items,
    // Avisa quem consome que o teto foi atingido, em vez de fingir completude.
    truncado: (primeira.pages || 1) > maxPaginas,
  };
}

export const brl = (v) =>
  (Number(v) || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const num = (v) => (Number(v) || 0).toLocaleString("pt-BR");

export const pct = (v) => `${(Number(v) || 0).toLocaleString("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
})}%`;

/** "2026-09-12T18:30:00+00:00" -> "12/09 18:30" */
export const dataHora = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

/** "2026-09-12" -> "12/09/2026" */
export const dataBR = (iso) => {
  const bruto = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(bruto)) return "—";
  const [a, m, d] = bruto.split("-");
  return `${d}/${m}/${a}`;
};

export const hoje = () => new Date().toISOString().slice(0, 10);
