import * as React from "react";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "./ui/sidebar";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

export function NavMain({
  items,
}: {
  items: {
    title: string;
    url: string;
    icon: React.ElementType;
    badge?: number | string;
    items?: { title: string; url: string; icon: React.ElementType }[];
  }[];
}) {
  const [openMenus, setOpenMenus] = React.useState<string[]>([]);
  const navigate = useNavigate();

  const toggleMenu = (title: string) => {
    setOpenMenus((prev) =>
      prev.includes(title) ? prev.filter((t) => t !== title) : [...prev, title]
    );
  };

  const { setOpenMobile } = useSidebar();

  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        const isOpen = openMenus.includes(item.title);
        const badgeText =
          item.badge === undefined || item.badge === null ? "" : String(item.badge);
        const hasBadge = badgeText.length > 0 && badgeText !== "0";
        const badgeTestId = `sidebar-badge-${item.title.toLowerCase().replace(/\s+/g, "-")}`;

        return (
          <React.Fragment key={item.title}>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                onClick={() => {
                  if (!item.items) {
                    navigate(item.url);
                    setOpenMobile(false);
                  } else {
                    toggleMenu(item.title);
                  }
                }}
                className="flex justify-between items-center"
              >
                <a className="flex w-full items-center">
                  <span className="flex items-center gap-2">
                    <Icon className="w-4 h-4" />
                    {item.title}
                  </span>
                  {hasBadge && (
                    <span
                      data-testid={badgeTestId}
                      className="ml-auto mr-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-destructive-foreground"
                    >
                      {badgeText}
                    </span>
                  )}
                  {item.items &&
                    (isOpen ? (
                      <ChevronDown className="w-4 h-4" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    ))}
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>

            {/* Submenu */}
            {item.items && isOpen && (
              <div className="ml-6 mt-1 space-y-1">
                {item.items.map((sub) => {
                  const SubIcon = sub.icon;
                  return (
                    <SidebarMenuItem key={sub.title}>
                      <SidebarMenuButton asChild>
                        <Link to={sub.url} className="flex items-center gap-2">
                          <SubIcon className="w-4 h-4" />
                          {sub.title}
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </div>
            )}
          </React.Fragment>
        );
      })}
    </SidebarMenu>
  );
}
