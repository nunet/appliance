import * as React from "react";
import {
  IconDashboard,
  IconListDetails,
  IconUsers,
  IconChartBar,
  IconServer,
  IconPlugConnected,
  IconCloudUpload,
  IconNetwork,
  IconBrowser,
} from "@tabler/icons-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "../components/ui/sidebar";
import { NavMain } from "../components/nav-main";
import { useNavigate } from "react-router-dom";
import { useAppMode } from "@/hooks/useAppMode";
import { CopyPlusIcon } from "lucide-react";
import { AdvancedModeToggle } from "./global/ModeToggle";
import { Button } from "./ui/button";
import { useAuth } from "@/hooks/useAuth";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const navigate = useNavigate();
  const { mode, setMode } = useAppMode();
  const { isMobile, setOpenMobile } = useSidebar();
  const { logout } = useAuth();

  const switchMode = () => {
    setMode(mode === "simple" ? "advanced" : "simple");
    navigate("/");
  };

  // Build nav structure dynamically depending on mode
  const navMain = [
    {
      title: "Dashboard",
      url: "/",
      icon: IconDashboard,
    },
    {
      title: "Deployments",
      url: "/deploy",
      icon: IconCloudUpload,  
    },
    {
      title: "Ensembles",
      url: "/ensembles",
      icon: IconChartBar,
    },
    {
      title: "Organizations",
      url: "/organizations",
      icon: IconUsers,
    },
    {
      title: "Contracts",
      url: "/contracts",
      icon: IconListDetails,
    },
  ];

  if (mode === "advanced") {
    navMain.push(
      {
        title: "Appliance",
        url: "/appliance",
        icon: IconServer,
        items: [
          { title: "DMS", url: "/appliance/dms", icon: IconServer },
          { title: "UPnP Port Forwarding", url: "/appliance/upnp", icon: IconNetwork },
          { title: "Proxy", url: "/appliance/proxy", icon: IconNetwork },
          { title: "DDNS", url: "/appliance/ddns", icon: IconNetwork },
          {
            title: "Onboarding Manager",
            url: "/appliance/onboarding",
            icon: IconBrowser,
          },
          { title: "Webserver", url: "/appliance/webserver", icon: IconServer },
          { title: "Plugins (coming soon)", url: "#", icon: IconPlugConnected },
        ],
      }
    );
  }

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          {/* Logo */}
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:!px-3 data-[slot=sidebar-menu-button]:!py-4 flex items-center justify-center overflow-visible"
              onClick={() => navigate("/")}
            >
              <a className="flex w-full items-center justify-center">
                <img
                  src="appliance-logo.png"
                  alt="NuNet Appliance logo"
                  className="h-auto w-full max-w-[180px] object-contain"
                />
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="pt-4 lg:pt-6">
        <NavMain items={navMain} />
      </SidebarContent>
      {isMobile && (
        <SidebarFooter className="mt-auto border-t border-sidebar-border p-4">
          <div className="flex flex-col gap-3">
            <AdvancedModeToggle />
            <Button
              variant="outline"
              onClick={() => {
                logout();
                setOpenMobile(false);
              }}
            >
              Log out
            </Button>
          </div>
        </SidebarFooter>
      )}
    </Sidebar>
  );
}
