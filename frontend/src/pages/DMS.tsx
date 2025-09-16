import { useState, useEffect } from "react";
import { Card, CardTitle } from "../components/ui/card";
import {
  RefreshCw,
  Square,
  Power,
  PowerOff,
  DownloadCloud,
  UploadCloud,
  Wrench,
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

export default function Page() {
  const actions = [
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

  const [logs, setLogs] = useState<string[]>([]);
  const [wsRef, setWsRef] = useState<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://127.0.0.1:8082");
    setWsRef(ws);

    ws.onopen = () => console.log("✅ WebSocket connected");

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "error") {
          setLogs((prev) => [...prev, `❌ Error: ${data.message}`]);
        } else if (data.type === "stdout" || data.type === "stderr") {
          setLogs((prev) => [...prev, data.data]);
        } else {
          setLogs((prev) => [...prev, JSON.stringify(data)]);
        }
      } catch {
        setLogs((prev) => [...prev, event.data]);
      }
    };

    ws.onclose = () => console.log("❌ WebSocket closed");
    ws.onerror = (err) => console.error("WebSocket error:", err);

    return () => ws.close();
  }, []);

  const sendResponse = (response: "y" | "n") => {
    if (wsRef && wsRef.readyState === WebSocket.OPEN) {
      wsRef.send(response);
      console.log(`Sent response: ${response}`);

      setLogs((prev) => {
        // Remove the last message (the one being replied to)
        const updated = [...prev];
        updated.pop();
        // Add the response we sent
        return [...updated];
      });
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-1 lg:px-6">
            {/* Action Buttons */}
            <Card>
              <div className="flex flex-wrap justify-center w-full gap-4 p-6">
                {actions.map(({ label, icon: Icon, color, api }) => (
                  <Button
                    key={label}
                    onClick={() => {
                      api().then((res) => {
                        toast(res.status, { description: res.message });
                      });
                    }}
                    className={`${color} text-white px-5 py-6 rounded-xl flex flex-row items-center justify-center shadow-md hover:scale-105 transition-transform`}
                  >
                    <Icon className="w-6 h-6 mr-2" />
                    <span className="text-sm font-medium">{label}</span>
                  </Button>
                ))}
              </div>
            </Card>

            {/* Logs + Yes/No */}
            {logs.length > 0 && (
              <Card className="p-4 rounded-xl shadow-md border border-gray-200">
                <CardTitle className="text-lg font-semibold mb-3">
                  DMS Says:
                </CardTitle>
                <div className="space-y-2 max-h-64 overflow-y-auto p-3 rounded-lg text-sm font-mono">
                  {logs.map((msg, index) => (
                    <div key={index} className="p-1">
                      {msg}
                    </div>
                  ))}
                </div>

                {/* Yes/No controls */}
                <div className="flex justify-end gap-3 mt-4">
                  <Button
                    variant="default"
                    onClick={() => sendResponse("y")}
                    className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg shadow-md"
                  >
                    Yes
                  </Button>
                  <Button
                    variant="default"
                    onClick={() => sendResponse("n")}
                    className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg shadow-md"
                  >
                    No
                  </Button>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
