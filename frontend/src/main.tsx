import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter, Routes, Route, Outlet, Navigate } from "react-router-dom";
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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DeploymentDetailsPage from "./pages/Deployment";
import Ensembles from "./pages/Ensembles";
import Wizzard from "./pages/Wizzard";
import { useAppMode } from "./hooks/useAppMode";
import NotFound from "./pages/NotFound";
import Organizations from "./pages/Organizations";
import PaymentsPage from "@/components/payments/PaymentsPage";

const queryClient = new QueryClient();

// Layout wrapper
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
      <SidebarInset>
        <SiteHeader />
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}

// Guard that redirects if no mode is chosen
// eslint-disable-next-line react-refresh/only-export-components
function ProtectedRoutes() {
  const { mode } = useAppMode();

  if (mode === "") {
    return <Navigate to="/wizzard" replace />;
  }

  return <Layout />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <Routes>
            {/* Wizard is accessible without mode */}
            <Route path="/wizzard" element={<Wizzard />} />

            {/* Everything else goes through ProtectedRoutes */}
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
          </Routes>
        </HashRouter>
      </QueryClientProvider>
      <Toaster />
    </ThemeProvider>
  </React.StrictMode>
);
