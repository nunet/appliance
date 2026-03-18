import { Button } from "../components/ui/button";
import { useAuth } from "../hooks/useAuth";
import { SidebarTrigger, useSidebar } from "../components/ui/sidebar";
import { AdvancedModeToggle } from "./global/ModeToggle";
import { ModeToggle } from "./mode-toggle";
import { PaymentsBadge } from "./payments/PaymentsBadge";
import { ConnectWalletButton } from "./payments/ConnectWalletButton";
import { Badge } from "../components/ui/badge";
import { useQuery } from "@tanstack/react-query";
import { getEnvironmentStatus } from "../api/api";

export function SiteHeader() {
  const { logout } = useAuth();
  const { isMobile } = useSidebar();
  const { data: environmentStatus, isError: environmentError } = useQuery({
    queryKey: ["sys", "environment"],
    queryFn: getEnvironmentStatus,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
    refetchOnMount: "always",
    staleTime: 30_000,
  });
  const isStaging = !environmentError && environmentStatus?.environment === "staging";

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <div className="ml-auto flex items-center gap-2">
          {isStaging && (
            <Badge variant="destructive" className="uppercase tracking-wide">
              Staging
            </Badge>
          )}
          <ConnectWalletButton />
          <PaymentsBadge />
          {!isMobile && <AdvancedModeToggle />}
          <ModeToggle />
          {!isMobile && (
            <Button variant="ghost" onClick={logout}>
              Log out
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
