import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import {
  HashRouter,
  Routes,
  Route,
  Outlet,
  Navigate,
  useLocation,
} from "react-router-dom";
import "./index.css";
import { ThemeProvider } from "./components/theme-provider";
import { Toaster } from "./components/ui/sonner";
import { SidebarInset, SidebarProvider } from "./components/ui/sidebar";
import { AppSidebar } from "./components/app-sidebar";
import { SiteHeader } from "./components/site-header";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { queryClient } from "./query-client";

const App = lazy(() => import("./pages/App"));
const DMS = lazy(() => import("./pages/DMS"));
const DeploymentsHistory = lazy(() => import("./pages/DeploymentsHistory"));
const NewDeployment = lazy(() => import("./pages/NewDeployment"));
const DeploymentDetailsPage = lazy(() => import("./pages/Deployment"));
const Ensembles = lazy(() => import("./pages/Ensembles"));
const NotFound = lazy(() => import("./pages/NotFound"));
const Organizations = lazy(() => import("./pages/Organizations"));
const Contracts = lazy(() => import("./pages/Contracts"));
const NewContractPage = lazy(() => import("./pages/Contracts/New"));
const PaymentsPage = lazy(() => import("./components/payments/PaymentsPage"));
const LoginPage = lazy(() => import("./pages/Login"));
const SetupAdmin = lazy(() => import("./pages/SetupAdmin"));
const UPnPPage = lazy(() => import("./pages/UPnP"));
const Appliance = lazy(() => import("./pages/Appliance"));
const Filesystem = lazy(() => import("./pages/Filesystem"));

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
          <Suspense fallback={<LoadingScreen />}>
            <HashRouter>
              <Routes>
                <Route path="/setup" element={<SetupRoute />} />
                <Route path="/login" element={<LoginRoute />} />

                <Route element={<RequireAuthWrapper />}>
                  <Route element={<ProtectedRoutes />}>
                    <Route path="*" element={<NotFound />} />
                    <Route path="/" element={<App />} />
                    <Route path="/deploy/" element={<DeploymentsHistory />} />
                    <Route path="/deploy/new" element={<NewDeployment />} />
                    <Route path="/deploy/:id" element={<DeploymentDetailsPage />} />
                    <Route path="/organizations" element={<Organizations />} />
                    <Route path="/ensembles" element={<Ensembles />} />
                    <Route path="/appliance" element={<Appliance />} />
                    <Route path="/appliance/dms" element={<DMS />} />
                    <Route path="/appliance/upnp" element={<UPnPPage />} />
                    <Route path="/appliance/filesystem" element={<Filesystem />} />
                    <Route path="/payments" element={<PaymentsPage />} />
                    <Route path="/contracts" element={<Contracts />} />
                    <Route path="/contracts/new" element={<NewContractPage />} />
                    <Route path="/contracts/new" element={<Contracts.NewContractPage />} />
                  </Route>
                </Route>
              </Routes>
            </HashRouter>
          </Suspense>
        </QueryClientProvider>
        <Toaster />
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
);
