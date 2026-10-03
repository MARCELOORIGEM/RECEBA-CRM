import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
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
        <Route path="/" element={<Dashboard />} />
        <Route path="/funil" element={<Pipeline />} />
        <Route path="/atividades" element={<Activities />} />
        <Route path="/restaurantes" element={<Restaurants />} />
        <Route path="/entregadores" element={<Drivers />} />
        <Route path="/formularios" element={<Forms />} />
        <Route path="/contratos-pagamentos" element={<Contracts />} />
        <Route path="/pedidos" element={<Orders />} />
        <Route path="/relatorios" element={<Reports />} />
        <Route path="/integracoes" element={<Integrations />} />
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
