import { createContext, useCallback, useContext, useRef, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

/**
 * Confirmação para ações destrutivas.
 *
 * Antes, clicar no ícone de lixeira apagava restaurante, entregador, contrato ou
 * pagamento na hora, sem pergunta e sem desfazer — um clique errado na tabela
 * levava o cadastro embora.
 *
 *   const confirmar = useConfirm();
 *   if (await confirmar({ titulo: "Excluir?", descricao: "..." })) del.mutate(id);
 */
const ConfirmContext = createContext(null);

const PADRAO = {
  titulo: "Confirmar ação",
  descricao: "Esta ação não pode ser desfeita.",
  confirmar: "Confirmar",
  cancelar: "Cancelar",
  destrutivo: true,
};

export function ConfirmProvider({ children }) {
  const [aberto, setAberto] = useState(false);
  const [opcoes, setOpcoes] = useState(PADRAO);
  const resolver = useRef(null);

  const confirmar = useCallback((config = {}) => {
    setOpcoes({ ...PADRAO, ...config });
    setAberto(true);
    return new Promise((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const responder = (valor) => {
    setAberto(false);
    resolver.current?.(valor);
    resolver.current = null;
  };

  return (
    <ConfirmContext.Provider value={confirmar}>
      {children}
      <AlertDialog open={aberto} onOpenChange={(v) => !v && responder(false)}>
        <AlertDialogContent
          className="bg-slate-900 border-slate-800 text-slate-100"
          data-testid="confirm-dialog"
        >
          <AlertDialogHeader>
            <AlertDialogTitle className="font-heading text-slate-50">
              {opcoes.titulo}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-slate-400">
              {opcoes.descricao}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => responder(false)}
              data-testid="confirm-cancel"
              className="bg-transparent border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-slate-100"
            >
              {opcoes.cancelar}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => responder(true)}
              data-testid="confirm-accept"
              className={
                opcoes.destrutivo
                  ? "bg-red-600 hover:bg-red-500 text-white"
                  : "bg-primary hover:bg-orange-600 text-white"
              }
            >
              {opcoes.confirmar}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmContext);
