import { useEffect } from "react";
import { useAppMode } from "@/hooks/useAppMode";
import { Card, CardContent } from "@/components/ui/card";
import { useNavigate } from "react-router-dom";

export default function Wizzard() {
  const { mode, setMode } = useAppMode();
  const navigate = useNavigate();
  const isAdvancedModeEnabled = false;

  // If user already picked a mode, skip this page
  useEffect(() => {
    if (mode !== "") {
      navigate("/", { replace: true }); // redirect home (or dashboard)
    }
  }, [mode, navigate]);

  const chooseMode = (m: "simple" | "advanced") => {
    if (m === "advanced" && !isAdvancedModeEnabled) {
      return;
    }
    setMode(m);
    navigate("/", { replace: true }); // redirect after picking
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-950">
      <h1 className="text-4xl font-bold mb-8 text-center text-white">
        Choose Your Mode
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-3xl px-4">
        {/* Red pill (Simple Mode) */}
        <Card
          onClick={() => chooseMode("simple")}
          className="cursor-pointer transition hover:scale-105 rounded-2xl border-2 border-red-500 bg-gradient-to-b from-red-600 to-red-800 shadow-xl"
        >
          <CardContent className="flex items-center justify-center h-48">
            <p className="text-2xl font-bold text-white">Simple Mode</p>
          </CardContent>
        </Card>

        {/* Blue pill (Advanced Mode) */}
        <Card
          onClick={isAdvancedModeEnabled ? () => chooseMode("advanced") : undefined}
          aria-disabled={!isAdvancedModeEnabled}
          className={`transition rounded-2xl border-2 border-blue-500 bg-gradient-to-b from-blue-600 to-blue-800 shadow-xl ${
            isAdvancedModeEnabled ? "cursor-pointer hover:scale-105" : "opacity-60 cursor-not-allowed pointer-events-none"
          }`}
        >
          <CardContent className="flex flex-col items-center justify-center h-48 gap-2">
            <p className="text-2xl font-bold text-white">Advanced Mode</p>
            {!isAdvancedModeEnabled ? (
              <span className="text-sm text-blue-100/80">Coming soon</span>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
