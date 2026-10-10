import { useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, CheckCircle2, Copy, Download, FileSpreadsheet, Loader2, RefreshCw, Upload,
  XCircle,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { dataBr, rotuloStatus } from "@/lib/funil";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/**
 * Baixa um arquivo da API pela sessão do usuário.
 *
 * Um <a href> direto não serve: no deploy com domínio separado a sessão vai
 * no cabeçalho, não só no cookie, e o link abriria a tela de login dentro do
 * download. Pelo axios o pedido leva a mesma autenticação das outras telas.
 */
async function baixar(url, nome) {
  const { data } = await api.get(url, { responseType: "blob" });
  const href = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = href;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

/** Menu "Baixar planilha": o modelo em branco ou o funil de hoje. */
export function BaixarPlanilha() {
  const [baixando, setBaixando] = useState(false);
  const executar = async (atual) => {
    setBaixando(true);
    try {
      // Data local, não UTC: depois das 21h em São Paulo o UTC já virou o dia
      // e o arquivo sairia com a data de amanhã. ("sv-SE" escreve AAAA-MM-DD.)
      const hoje = new Date().toLocaleDateString("sv-SE");
      await baixar(
        `/leads/modelo${atual ? "?atual=true" : ""}`,
        atual ? `funil-${hoje}.xlsx` : "modelo-importacao-funil.xlsx",
      );
    } catch (e) {
      toast.error(apiError(e, "Não foi possível baixar a planilha."));
    } finally {
      setBaixando(false);
    }
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          disabled={baixando}
          data-testid="btn-baixar-planilha"
          className="border-slate-700 gap-2"
        >
          {baixando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          Baixar planilha
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 bg-slate-900 border-slate-800">
        <DropdownMenuItem
          onSelect={() => executar(false)}
          data-testid="baixar-modelo"
          className="flex-col items-start gap-0.5 py-2"
        >
          <span className="text-sm text-slate-100">Modelo em branco</span>
          <span className="text-xs text-slate-500">Colunas, exemplos e instruções para preencher</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => executar(true)}
          data-testid="baixar-funil-atual"
          className="flex-col items-start gap-0.5 py-2"
        >
          <span className="text-sm text-slate-100">Funil atual</span>
          <span className="text-xs text-slate-500">Os leads de hoje no mesmo formato — edite o STATUS e importe de volta</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Contador({ icon: Icon, valor, rotulo, tom }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <Icon className={`h-5 w-5 shrink-0 ${tom}`} aria-hidden="true" />
      <div>
        <p className="font-heading text-xl font-bold text-slate-100">{valor}</p>
        <p className="text-xs text-slate-500">{rotulo}</p>
      </div>
    </div>
  );
}

function ListaDeLinhas({ titulo, itens, tom, testid }) {
  if (!itens.length) return null;
  return (
    <div className="space-y-2" data-testid={testid}>
      <p className={`text-sm font-medium ${tom}`}>{titulo}</p>
      <ul className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/50 p-2 text-xs">
        {itens.map((e) => (
          <li key={`${e.linha}-${e.nome}`} className="flex gap-2">
            <span className="shrink-0 font-mono text-slate-500">linha {e.linha}</span>
            <span className="text-slate-300">
              <strong className="text-slate-200">{e.nome}</strong> — {e.motivo}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Importação em dois tempos: o arquivo vai primeiro em SIMULAÇÃO, a tela mostra
 * o que entra, o que tem erro e o que já existe, e só ao confirmar o mesmo
 * arquivo é enviado para gravar. Errar uma coluna não vira duzentos leads
 * tortos no funil.
 */
export function ImportarLeads({ aberto, onFechar, onImportado }) {
  const [arquivo, setArquivo] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [arrastando, setArrastando] = useState(false);
  const entrada = useRef(null);

  const limpar = () => {
    setArquivo(null);
    setPrevia(null);
    setCarregando(false);
  };

  const enviar = async (f, simular) => {
    const corpo = new FormData();
    corpo.append("arquivo", f);
    // Sem Content-Type à mão: o navegador monta o multipart com o separador
    // (boundary); fixado aqui, o servidor não acharia onde o arquivo começa.
    const { data } = await api.post(`/leads/importar?simular=${simular}`, corpo);
    return data;
  };

  const escolher = async (f) => {
    if (!f) return;
    setArquivo(f);
    setPrevia(null);
    setCarregando(true);
    try {
      setPrevia(await enviar(f, true));
    } catch (e) {
      toast.error(apiError(e, "Não foi possível ler a planilha."));
      setArquivo(null);
    } finally {
      setCarregando(false);
    }
  };

  const confirmar = async () => {
    setCarregando(true);
    try {
      const r = await enviar(arquivo, false);
      const partes = [];
      if (r.importados) partes.push(`${r.importados} novo(s)`);
      if (r.atualizados_gravados) partes.push(`${r.atualizados_gravados} atualizado(s)`);
      toast.success(`Planilha importada: ${partes.join(" e ")}`);
      onImportado?.();
      limpar();
      onFechar();
    } catch (e) {
      toast.error(apiError(e, "A importação falhou. Nada foi gravado."));
      setCarregando(false);
    }
  };

  const copiarErros = async () => {
    const texto = [...(previa?.erros || []), ...(previa?.duplicados || [])]
      .map((e) => `Linha ${e.linha} — ${e.nome}: ${e.motivo}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(texto);
      toast.success("Lista copiada");
    } catch {
      toast.error("Copie manualmente.");
    }
  };

  return (
    <Dialog
      open={aberto}
      onOpenChange={(v) => {
        if (!v && !carregando) {
          limpar();
          onFechar();
        }
      }}
    >
      <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-primary" aria-hidden="true" />
            Importar planilha de leads
          </DialogTitle>
        </DialogHeader>

        {!previa && (
          <div className="space-y-4">
            <button
              type="button"
              onClick={() => entrada.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setArrastando(true);
              }}
              onDragLeave={() => setArrastando(false)}
              onDrop={(e) => {
                e.preventDefault();
                setArrastando(false);
                escolher(e.dataTransfer.files?.[0]);
              }}
              disabled={carregando}
              data-testid="importar-area"
              className={`flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
                arrastando ? "border-primary bg-primary/10" : "border-slate-700 hover:border-slate-500"
              }`}
            >
              {carregando ? (
                <Loader2 className="h-8 w-8 animate-spin text-primary" aria-hidden="true" />
              ) : (
                <Upload className="h-8 w-8 text-slate-400" aria-hidden="true" />
              )}
              <span className="text-sm text-slate-200">
                {carregando ? `Lendo ${arquivo?.name}…` : "Clique para escolher ou arraste o arquivo aqui"}
              </span>
              <span className="text-xs text-slate-500">
                Excel (.xlsx) ou CSV • até 2.000 leads • LEAD ID que já existe atualiza o lead •
                nada é gravado antes de você conferir
              </span>
            </button>
            <input
              ref={entrada}
              type="file"
              accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
              className="hidden"
              data-testid="importar-arquivo"
              onChange={(e) => {
                escolher(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
              <span>Ainda não tem a planilha? Baixe o modelo com as colunas certas e os exemplos.</span>
              <BaixarPlanilha />
            </div>
          </div>
        )}

        {previa && (
          <div className="space-y-5" data-testid="importar-previa">
            <p className="text-sm text-slate-400">
              <strong className="text-slate-200">{arquivo?.name}</strong> — {previa.total} linha(s)
              com dados. Confira antes de importar.
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Contador icon={CheckCircle2} valor={previa.novos} rotulo="leads novos" tom="text-emerald-400" />
              <Contador icon={RefreshCw} valor={previa.atualizados.length} rotulo="serão atualizados (mesmo LEAD ID)" tom="text-sky-400" />
              <Contador icon={AlertTriangle} valor={previa.duplicados.length} rotulo="repetidos (ignorados)" tom="text-amber-400" />
              <Contador icon={XCircle} valor={previa.erros.length} rotulo="com erro (ignorados)" tom="text-red-400" />
            </div>
            {previa.inalterados > 0 && (
              <p className="text-xs text-slate-500">
                {previa.inalterados} lead(s) da planilha já estão no funil exatamente iguais — nada muda neles.
              </p>
            )}

            {previa.colunas_ignoradas.length > 0 && (
              <p className="rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-xs text-slate-400">
                Colunas não reconhecidas, ignoradas: {previa.colunas_ignoradas.join(", ")}
              </p>
            )}

            {previa.previa.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-slate-200">
                  Prévia {previa.novos > previa.previa.length && `(primeiros ${previa.previa.length} de ${previa.novos})`}
                </p>
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950/60 text-slate-500">
                      <tr>
                        {["Linha", "Lead ID", "Nome lead", "Bairro", "Nome BD", "Líder", "Data visita", "Status"].map((h) => (
                          <th key={h} className="px-2 py-2 font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previa.previa.map((l) => (
                        <tr key={l.linha} className="border-t border-slate-800 text-slate-300">
                          <td className="px-2 py-1.5 font-mono text-slate-500">{l.linha}</td>
                          <td className="px-2 py-1.5 font-mono">{l.codigo_externo || "—"}</td>
                          <td className="px-2 py-1.5 text-slate-100">{l.name}</td>
                          <td className="px-2 py-1.5">{l.bairro || "—"}</td>
                          <td className="px-2 py-1.5">{l.bd_nome || "—"}</td>
                          <td className="px-2 py-1.5">{l.lider || "—"}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{dataBr(l.data_visita) || "—"}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{rotuloStatus(l.stage)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {previa.atualizados.length > 0 && (
              <div className="space-y-2" data-testid="importar-atualizados">
                <p className="text-sm font-medium text-sky-400">
                  Serão atualizados — o LEAD ID já está no funil
                </p>
                <ul className="max-h-48 space-y-1.5 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/50 p-2 text-xs">
                  {previa.atualizados.map((a) => (
                    <li key={`${a.linha}-${a.codigo}`}>
                      <span className="font-mono text-slate-500">linha {a.linha}</span>{" "}
                      <strong className="text-slate-200">{a.nome}</strong>{" "}
                      <span className="font-mono text-slate-500">({a.codigo})</span>
                      <ul className="ml-4 mt-0.5 list-disc text-slate-400">
                        {a.mudancas.map((m) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <ListaDeLinhas titulo="Com erro — corrija na planilha e importe de novo" itens={previa.erros} tom="text-red-400" testid="importar-erros" />
            <ListaDeLinhas titulo="Repetidos — já estão no funil ou duplicados na planilha" itens={previa.duplicados} tom="text-amber-400" testid="importar-duplicados" />
            {(previa.erros.length > 0 || previa.duplicados.length > 0) && (
              <Button variant="ghost" size="sm" onClick={copiarErros} className="h-7 gap-1.5 text-xs text-slate-400">
                <Copy className="h-3.5 w-3.5" /> Copiar lista de linhas ignoradas
              </Button>
            )}
          </div>
        )}

        <DialogFooter className="gap-2">
          {previa && (
            <Button variant="ghost" onClick={limpar} disabled={carregando} className="text-slate-400">
              Escolher outro arquivo
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() => {
              limpar();
              onFechar();
            }}
            disabled={carregando}
            className="border-slate-700"
          >
            Cancelar
          </Button>
          {previa && (
            <Button
              onClick={confirmar}
              disabled={carregando || previa.novos + previa.atualizados.length === 0}
              data-testid="importar-confirmar"
              className="bg-primary hover:bg-orange-600 text-white gap-2"
            >
              {carregando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              {previa.novos + previa.atualizados.length === 0
                ? "Nada para importar"
                : (() => {
                    const texto = [
                      previa.novos ? `importar ${previa.novos} novo(s)` : "",
                      previa.atualizados.length ? `atualizar ${previa.atualizados.length}` : "",
                    ].filter(Boolean).join(" e ");
                    return texto.charAt(0).toUpperCase() + texto.slice(1);
                  })()}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
