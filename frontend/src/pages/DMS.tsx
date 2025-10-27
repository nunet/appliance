import { useState } from "react";
import { Card, CardTitle } from "../components/ui/card";
import {
  RefreshCw,
  Square,
  Power,
  PowerOff,
  DownloadCloud,
  UploadCloud,
  Wrench,
  LucideIcon,
} from "lucide-react";
import {
  restartDms,
  stopDms,
  enableDms,
  disableDms,
  onboardCompute,
  offboardCompute,
  initDms,
  updateDms,
} from "../api/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";

type Action = {
  label: string;
  icon: LucideIcon;
  color: string;
  api: () => Promise<{ status: string; message?: string }>;
};

const actions: Action[] = [
  {
    label: "Restart",
    icon: RefreshCw,
    color: "bg-blue-500 hover:bg-blue-600",
    api: restartDms,
  },
  {
    label: "Stop",
    icon: Square,
    color: "bg-red-500 hover:bg-red-600",
    api: stopDms,
  },
  {
    label: "Enable",
    icon: Power,
    color: "bg-green-500 hover:bg-green-600",
    api: enableDms,
  },
  {
    label: "Disable",
    icon: PowerOff,
    color: "bg-gray-500 hover:bg-gray-600",
    api: disableDms,
  },
  {
    label: "Onboard",
    icon: DownloadCloud,
    color: "bg-indigo-500 hover:bg-indigo-600",
    api: onboardCompute,
  },
  {
    label: "Offboard",
    icon: UploadCloud,
    color: "bg-yellow-500 hover:bg-yellow-600 text-black",
    api: offboardCompute,
  },
  {
    label: "Init",
    icon: Wrench,
    color: "bg-purple-500 hover:bg-purple-600",
    api: initDms,
  },
  {
    label: "Update",
    icon: RefreshCw,
    color: "bg-pink-500 hover:bg-pink-600",
    api: updateDms,
  },
];

export default function Page() {
  const [logs, setLogs] = useState<string[]>([]);

  const appendLog = (entry: string) => {
    setLogs((prev) => {
      const next = [entry, ...prev];
      return next.slice(0, 100);
    });
  };

  const runAction = async (action: Action) => {
    try {
      const res = await action.api();
      const status = res?.status ?? "success";
      const description = res?.message ?? "Command completed.";
      toast(status, { description });
      appendLog(`[${action.label}] ${description}`);
    } catch (err) {
      console.error(`Failed to run ${action.label}:`, err);
      const description =
        err instanceof Error
          ? err.message
          : typeof err === "object" && err !== null && "message" in err
          ? String((err as any).message)
          : "Unexpected error";
      toast("error", { description });
      appendLog(`[${action.label}] ERROR: ${description}`);
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-1 lg:px-6">
            <Card>
              <div className="flex flex-wrap justify-center w-full gap-4 p-6">
                {actions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <Button
                      key={action.label}
                      onClick={() => runAction(action)}
                      className={`${action.color} text-white px-5 py-6 rounded-xl flex flex-row items-center justify-center shadow-md hover:scale-105 transition-transform`}
                    >
                      <Icon className="w-6 h-6 mr-2" />
                      <span className="text-sm font-medium">{action.label}</span>
                    </Button>
                  );
                })}
              </div>
            </Card>

            {logs.length > 0 && (
              <Card className="p-4 rounded-xl shadow-md border border-gray-200">
                <CardTitle className="text-lg font-semibold mb-3">
                  Recent Activity
                </CardTitle>
                <div className="space-y-2 max-h-64 overflow-y-auto p-3 rounded-lg text-sm font-mono bg-slate-50">
                  {logs.map((msg, index) => (
                    <div key={index} className="p-1 break-words">
                      {msg}
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
