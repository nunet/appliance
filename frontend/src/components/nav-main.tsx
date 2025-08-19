import * as React from "react";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "./ui/sidebar";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

export function NavMain({
  items,
}: {
  items: {
    title: string;
    url: string;
    icon: React.ElementType;
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

  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        const isOpen = openMenus.includes(item.title);

        return (
          <React.Fragment key={item.title}>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                onClick={() =>
                  item.items ? toggleMenu(item.title) : navigate(item.url)
                }
                className="flex justify-between items-center"
              >
                <a>
                  <span className="flex items-center gap-2">
                    <Icon className="w-4 h-4" />
                    {item.title}
                  </span>
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
