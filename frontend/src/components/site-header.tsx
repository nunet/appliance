import { Separator } from "../components/ui/separator";
import { Button } from "../components/ui/button";
import { useAuth } from "../hooks/useAuth";
import { SidebarTrigger } from "../components/ui/sidebar";
import { AdvancedModeToggle } from './global/ModeToggle';
import { ModeToggle } from "./mode-toggle";
import { PaymentsBadge } from "./payments/PaymentsBadge";
import { ConnectWalletButton } from "./payments/ConnectWalletButton";

export function SiteHeader() {
  const { logout } = useAuth();

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mx-2 data-[orientation=vertical]:h-4"
        />
        <h1 className="text-base font-medium">🚀 Dashboard</h1>
        <div className="ml-auto flex items-center gap-2">
          <ConnectWalletButton />
          <PaymentsBadge />
          <AdvancedModeToggle />
          <ModeToggle />
          <Button variant="ghost" onClick={logout}>
            Log out
          </Button>
        </div>
      </div>
    </header>
  );
}
