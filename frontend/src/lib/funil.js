/**
 * Status do Funil — a régua da visita de campo.
 *
 * Espelha STATUS de backend/app/funil.py (as chaves precisam bater; o banco
 * recusa qualquer outra). Grupo: "aberto" em trabalho, "ganho" ativado,
 * "perdido" descartado.
 *
 * As classes do Tailwind ficam escritas por extenso: ele só gera CSS para
 * classe que aparece literal no código, e montada por concatenação
 * ("border-t-" + cor) ela sumiria do build.
 */
export const STATUS = [
  { chave: "a_visitar", rotulo: "A visitar", grupo: "aberto",
    borda: "border-t-slate-400", badge: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
  { chave: "nao_localizado", rotulo: "Não localizado", grupo: "aberto",
    borda: "border-t-orange-500", badge: "bg-orange-500/15 text-orange-300 border-orange-500/30" },
  { chave: "fechado_no_local", rotulo: "Fechado no local", grupo: "aberto",
    borda: "border-t-stone-400", badge: "bg-stone-500/15 text-stone-300 border-stone-500/30" },
  { chave: "responsavel_ausente", rotulo: "Responsável ausente", grupo: "aberto",
    borda: "border-t-yellow-500", badge: "bg-yellow-500/15 text-yellow-300 border-yellow-500/30" },
  { chave: "colhendo_dados", rotulo: "Colhendo dados", grupo: "aberto",
    borda: "border-t-sky-500", badge: "bg-sky-500/15 text-sky-300 border-sky-500/30" },
  { chave: "reuniao", rotulo: "Reunião", grupo: "aberto",
    borda: "border-t-blue-500", badge: "bg-blue-500/15 text-blue-300 border-blue-500/30" },
  { chave: "segunda_visita", rotulo: "Segunda visita", grupo: "aberto",
    borda: "border-t-indigo-500", badge: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30" },
  { chave: "aguardando_documentos", rotulo: "Aguardando documentos", grupo: "aberto",
    borda: "border-t-amber-500", badge: "bg-amber-500/15 text-amber-300 border-amber-500/30" },
  { chave: "cadastro_enviado", rotulo: "Cadastro enviado", grupo: "aberto",
    borda: "border-t-violet-500", badge: "bg-violet-500/15 text-violet-300 border-violet-500/30" },
  { chave: "ativado", rotulo: "Ativado", grupo: "ganho",
    borda: "border-t-emerald-500", badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  { chave: "sem_interesse", rotulo: "Sem interesse", grupo: "perdido", pedeMotivo: true,
    borda: "border-t-red-500", badge: "bg-red-500/15 text-red-300 border-red-500/30" },
  { chave: "ja_parceiro", rotulo: "Já é parceiro", grupo: "perdido",
    borda: "border-t-teal-500", badge: "bg-teal-500/15 text-teal-300 border-teal-500/30" },
  { chave: "fora_da_area", rotulo: "Fora da área", grupo: "perdido",
    borda: "border-t-rose-500", badge: "bg-rose-500/15 text-rose-300 border-rose-500/30" },
];

export const POR_CHAVE = Object.fromEntries(STATUS.map((s) => [s.chave, s]));
export const INICIAL = "a_visitar";
export const GANHO = "ativado";

// Etapas da versão anterior, que ainda podem aparecer no histórico de um lead.
const LEGADO = {
  novo: "Novo", contatado: "Contatado", negociacao: "Em negociação",
  proposta: "Proposta", ganho: "Ganho", perdido: "Perdido",
};

export const rotuloStatus = (chave) => POR_CHAVE[chave]?.rotulo || LEGADO[chave] || chave || "—";

export const ORIGENS = [
  ["indicacao", "Indicação"],
  ["instagram", "Instagram"],
  ["prospeccao", "Prospecção ativa"],
  ["site", "Site"],
  ["whatsapp", "WhatsApp"],
  ["evento", "Evento"],
  ["outro", "Outro"],
];

/** "2026-10-05" -> "05/10/2026", sem passar por Date (que mudaria o dia pelo fuso). */
export function dataBr(iso) {
  if (!iso) return "";
  const [a, m, d] = String(iso).slice(0, 10).split("-");
  return a && m && d ? `${d}/${m}/${a}` : iso;
}
