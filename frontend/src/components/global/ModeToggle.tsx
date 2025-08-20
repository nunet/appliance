"use client";

import { useAppMode } from "@/hooks/useAppMode";
import { Switch } from "@/components/ui/switch";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

export function AdvancedModeToggle() {
  const { mode, setMode } = useAppMode();
  const [enabled, setEnabled] = useState(mode === "advanced");
  const navigate = useNavigate();

  // Sync local state with persisted mode
  useEffect(() => {
    setEnabled(mode === "advanced");
  }, [mode]);

  const handleToggle = (value: boolean) => {
    setEnabled(value);
    setMode(value ? "advanced" : "simple");
    navigate("/");
  };

  return (
    <div className="flex flex-row items-center gap-2">
      <span className="text-xs font-medium text-gray-300">Advanced</span>
      <Switch checked={enabled} onCheckedChange={handleToggle} />
    </div>
  );
}
