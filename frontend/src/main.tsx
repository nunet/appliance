import React from "react";
import ReactDOM from "react-dom/client";
import {
  HashRouter,
  Routes,
  Route,
  Outlet,
  Navigate,
  useLocation,
} from "react-router-dom";
import App from "./pages/App";
import DMS from "./pages/DMS";
import DeploymentsHistory from "./pages/DeploymentsHistory";
import NewDeployment from "./pages/NewDeployment";
import "./index.css";
import { ThemeProvider } from "./components/theme-provider";
import { Toaster } from "./components/ui/sonner";
import { SidebarInset, SidebarProvider } from "./components/ui/sidebar";
import { AppSidebar } from "./components/app-sidebar";
import { SiteHeader } from "./components/site-header";
import { QueryClientProvider } from "@tanstack/react-query";
import DeploymentDetailsPage from "./pages/Deployment";
import Ensembles from "./pages/Ensembles";
import Wizzard from "./pages/Wizzard";
import { useAppMode } from "./hooks/useAppMode";
import NotFound from "./pages/NotFound";
import Organizations from "./pages/Organizations";
import PaymentsPage from "@/components/payments/PaymentsPage";
import LoginPage from "./pages/Login";
import SetupAdmin from "./pages/SetupAdmin";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { queryClient } from "./query-client";

function Layout() {
  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "16rem",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset className="overflow-x-hidden md:overflow-x-visible">
        <SiteHeader />
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
function ProtectedRoutes() {
  const { mode } = useAppMode();

  if (mode === "") {
    return <Navigate to="/wizzard" replace />;
  }

  return <Layout />;
}

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center text-muted-foreground">
      Loading...
    </div>
  );
}

function RequireAuthWrapper() {
  const { loading, passwordSet, token } = useAuth();
  const location = useLocation();

  if (loading) {
    return <LoadingScreen />;
  }

  if (!passwordSet) {
    return <Navigate to="/setup" replace />;
  }

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}

function SetupRoute() {
  const { loading, passwordSet } = useAuth();

  if (loading) {
    return <LoadingScreen />;
  }

  if (passwordSet) {
    return <Navigate to="/login" replace />;
  }

  return <SetupAdmin />;
}

function LoginRoute() {
  const { loading, passwordSet, token } = useAuth();
  const location = useLocation();

  if (loading) {
    return <LoadingScreen />;
  }

  if (!passwordSet) {
    return <Navigate to="/setup" replace />;
  }

  if (token) {
    const redirectTo = (location.state as { from?: { pathname?: string } })?.from?.pathname ?? "/";
    return <Navigate to={redirectTo} replace />;
  }

  return <LoginPage />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <HashRouter>
            <Routes>
              <Route path="/setup" element={<SetupRoute />} />
              <Route path="/login" element={<LoginRoute />} />

              <Route element={<RequireAuthWrapper />}>
                <Route path="/wizzard" element={<Wizzard />} />

                <Route element={<ProtectedRoutes />}>
                  <Route path="*" element={<NotFound />} />
                  <Route path="/" element={<App />} />
                  <Route path="/deploy/" element={<DeploymentsHistory />} />
                  <Route path="/deploy/new" element={<NewDeployment />} />
                  <Route path="/deploy/:id" element={<DeploymentDetailsPage />} />
                  <Route path="/organizations" element={<Organizations />} />
                  <Route path="/ensembles" element={<Ensembles />} />
                  <Route path="/appliance/dms" element={<DMS />} />
                  <Route path="/payments" element={<PaymentsPage />} />
                </Route>
              </Route>
            </Routes>
          </HashRouter>
        </QueryClientProvider>
        <Toaster />
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
);
