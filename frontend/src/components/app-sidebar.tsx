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
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "../components/ui/sidebar";
import { NavMain } from "../components/nav-main";
import { useNavigate } from "react-router-dom";
import { useAppMode } from "@/hooks/useAppMode";
import { CopyPlusIcon } from "lucide-react";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const navigate = useNavigate();
  const { mode, setMode } = useAppMode();

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
      items: [
        {
          title: "New Deployment",
          url: "/deploy/new",
          icon: CopyPlusIcon,
        },
        {
          title: "Deployments History",
          url: "/deploy/history",
          icon: IconListDetails,
        },
      ],
    },
    {
      title: "Organizations",
      url: "/organizations",
      icon: IconUsers,
    },
  ];

  if (mode === "advanced") {
    navMain.push(
      {
        title: "Ensembles",
        url: "/ensembles",
        icon: IconChartBar,
      },
      {
        title: "Appliance",
        url: "/appliance",
        icon: IconServer,
        items: [
          { title: "DMS", url: "/appliance/dms", icon: IconServer },
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
              className="data-[slot=sidebar-menu-button]:!p-1.5 flex items-center justify-center"
              onClick={() => navigate("/")}
            >
              <a>
                <span>
                  <img
                    src="nunet_logo.png"
                    className="w-24 h-24 object-contain"
                  />
                </span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>

          {/* Switch mode button */}
          <SidebarMenuItem className="mt-2">
            <button
              onClick={switchMode}
              className="w-full rounded-md bg-white text-gray-900 font-medium py-1.5 px-3 text-sm shadow hover:bg-gray-100 transition"
            >
              Switch to {mode === "simple" ? "Advanced" : "Simple"} Mode
            </button>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <NavMain items={navMain} />
      </SidebarContent>
    </Sidebar>
  );
}
