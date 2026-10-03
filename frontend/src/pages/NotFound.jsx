import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div
      className="min-h-[60vh] flex flex-col items-center justify-center text-center gap-4"
      data-testid="not-found-page"
    >
      <div className="w-14 h-14 rounded-2xl bg-slate-800/60 flex items-center justify-center">
        <Compass className="w-7 h-7 text-slate-500" aria-hidden="true" />
      </div>
      <div>
        <h2 className="font-heading text-2xl font-bold text-slate-50">Página não encontrada</h2>
        <p className="text-sm text-slate-500 mt-1">
          O endereço acessado não existe no painel. Use o menu ou a busca (Ctrl + K).
        </p>
      </div>
      <Button asChild className="bg-primary hover:bg-orange-600 text-white">
        <Link to="/">Voltar ao dashboard</Link>
      </Button>
    </div>
  );
}
