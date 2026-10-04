import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Loader2, Lock } from "lucide-react";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ConfirmProvider } from "@/components/ConfirmDialog";
import ErrorBoundary from "@/components/ErrorBoundary";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Pipeline from "@/pages/Pipeline";
import Activities from "@/pages/Activities";
import Restaurants from "@/pages/Restaurants";
import Drivers from "@/pages/Drivers";
import Contracts from "@/pages/Contracts";
import Orders from "@/pages/Orders";
import Reports from "@/pages/Reports";
import Integrations from "@/pages/Integrations";
import Users from "@/pages/Users";
import Forms from "@/pages/Forms";
import PublicForm from "@/pages/PublicForm";
import ResetPassword from "@/pages/ResetPassword";
import NotFound from "@/pages/NotFound";
import { primeiraRota } from "@/lib/permissoes";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0C0D0F]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" aria-label="Carregando" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/**
 * Tela liberada só para quem tem o módulo. Sem ele, manda para a primeira tela
 * que o usuário pode abrir — e não para "/", que pode ser justamente uma tela
 * proibida (o Dashboard mostra receita, e nem todo gestor deve vê-la).
 */
function Exige({ modulo, children }) {
  const { pode } = useAuth();
  if (pode(modulo)) return children;
  const destino = primeiraRota(pode);
  if (destino) return <Navigate to={destino} replace />;
  return <SemAcesso />;
}

function SemAcesso() {
  return (
    <div className="mx-auto mt-16 max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
      <Lock className="mx-auto h-8 w-8 text-slate-500" aria-hidden="true" />
      <h2 className="mt-4 font-heading text-lg font-bold text-slate-100">Nenhuma tela liberada</h2>
      <p className="mt-2 text-sm text-slate-400">
        Sua conta existe, mas o administrador ainda não liberou nenhuma tela para você.
      </p>
    </div>
  );
}

function AdminOnly({ children }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Navigate to="/" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Fora da área autenticada de propósito: quem recebe este link não tem
          conta no sistema e não deve precisar de uma para se cadastrar. */}
      <Route path="/f/:slug" element={<PublicForm />} />
      {/* Também público: quem chega aqui é exatamente quem não consegue
          entrar. O token da URL é a credencial. */}
      <Route path="/redefinir-senha/:token" element={<ResetPassword />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Exige modulo="dashboard"><Dashboard /></Exige>} />
        <Route path="/funil" element={<Exige modulo="funil"><Pipeline /></Exige>} />
        <Route path="/atividades" element={<Exige modulo="atividades"><Activities /></Exige>} />
        <Route path="/restaurantes" element={<Exige modulo="restaurantes"><Restaurants /></Exige>} />
        <Route path="/entregadores" element={<Exige modulo="entregadores"><Drivers /></Exige>} />
        <Route path="/formularios" element={<Exige modulo="formularios"><Forms /></Exige>} />
        <Route path="/contratos-pagamentos" element={<Exige modulo="financeiro"><Contracts /></Exige>} />
        <Route path="/pedidos" element={<Exige modulo="pedidos"><Orders /></Exige>} />
        <Route path="/relatorios" element={<Exige modulo="relatorios"><Reports /></Exige>} />
        <Route path="/integracoes" element={<Exige modulo="integracoes"><Integrations /></Exige>} />
        <Route
          path="/usuarios"
          element={
            <AdminOnly>
              <Users />
            </AdminOnly>
          }
        />
        {/* Rota desconhecida mostra uma página, em vez de redirecionar em
            silêncio para o dashboard e dar a impressão de que o link sumiu. */}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function App() {
  // A classe `dark` fica no <html> (public/index.html), não aqui: componentes
  // Radix montam em portal no <body> e, presos a este div, saíam claros sobre
  // o app escuro — era o caso da paleta de busca.
  return (
    <div className="App">
      <ErrorBoundary>
        <AuthProvider>
          <ConfirmProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </ConfirmProvider>
          <Toaster position="top-right" richColors theme="dark" closeButton />
        </AuthProvider>
      </ErrorBoundary>
    </div>
  );
}

export default App;
