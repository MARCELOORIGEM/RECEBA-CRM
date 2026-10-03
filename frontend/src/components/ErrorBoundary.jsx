import { Component } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Sem isto, qualquer exceção de render deixava a tela em branco — o usuário via
 * um retângulo preto e nenhuma indicação do que fazer.
 */
export class ErrorBoundary extends Component {
  state = { erro: null };

  static getDerivedStateFromError(erro) {
    return { erro };
  }

  componentDidCatch(erro, info) {
    // eslint-disable-next-line no-console
    console.error("Falha na interface:", erro, info?.componentStack);
  }

  render() {
    if (!this.state.erro) return this.props.children;
    return (
      <div
        className="min-h-[60vh] flex flex-col items-center justify-center gap-4 px-6 text-center"
        data-testid="error-boundary"
      >
        <div className="w-14 h-14 rounded-2xl bg-red-500/15 flex items-center justify-center">
          <AlertTriangle className="w-7 h-7 text-red-400" />
        </div>
        <div>
          <h2 className="font-heading text-xl font-bold text-slate-50">
            Esta tela encontrou um erro
          </h2>
          <p className="text-sm text-slate-400 mt-1 max-w-md">
            O restante do sistema continua funcionando. Recarregue a página; se
            insistir, avise o time com o horário em que aconteceu.
          </p>
          <p className="mt-3 font-mono text-xs text-slate-600 break-all max-w-lg">
            {String(this.state.erro?.message || this.state.erro)}
          </p>
        </div>
        <Button
          onClick={() => window.location.reload()}
          className="bg-primary hover:bg-orange-600 text-white gap-2"
        >
          <RotateCcw className="w-4 h-4" /> Recarregar
        </Button>
      </div>
    );
  }
}

export default ErrorBoundary;
