import { useEffect } from "react";
import { AppSidebar } from "../components/app-sidebar";
// import { ChartAreaInteractive } from "../components/chart-area-interactive";
import { DataTable } from "../components/data-table";
import { SectionCards } from "../components/section-cards";
import { SiteHeader } from "../components/site-header";
import { Card, CardFooter, CardTitle } from "../components/ui/card";
import { SidebarInset, SidebarProvider } from "../components/ui/sidebar";
import { getTemplates } from "../api/deployments";
import React from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import DeploymentsTable from "../components/deployments/DeploymentsTable";
import { Button } from "../components/ui/button";

import { useQuery } from "@tanstack/react-query";

// eslint-disable-next-line react-refresh/only-export-components
export function useTemplates() {
  return useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      const response = await getTemplates();
      return response.items;
    },
    staleTime: Infinity, // data never considered stale
    gcTime: Infinity, // keep cached forever (formerly cacheTime)
  });
}

export default function Page() {
  const { data: templates = [], isLoading, isError } = useTemplates();
  const [selectedTemplate, setSelectedTemplate] = React.useState("");
  const connectDeployWebSocket = (file, timeout = 60) => {
    const ws = new WebSocket(
      `${
        import.meta.env.VITE_SOCKET_URL
      }/ensemble/ws/deploy?file=${encodeURIComponent(file)}&timeout=${timeout}`
    );
    ws.onopen = () => {
      console.log("WebSocket connected");
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("Message from server:", data);
      } catch {
        console.log("Raw message:", event.data);
      }
    };
    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
    ws.onclose = () => {
      console.log("WebSocket closed");
    };
    return ws;
  };

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 lg:px-6 items-start">
            {/* Card 1 → default goes second on small, first on lg */}
            <Card className="lg:col-span-3 px-3">
              <CardTitle>Deployments</CardTitle>
              <DeploymentsTable />
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
