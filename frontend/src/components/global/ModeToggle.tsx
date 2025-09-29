"use client";

import { useAppMode } from "@/hooks/useAppMode";
import { Switch } from "@/components/ui/switch";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const isAdvancedModeEnabled = false;
const isAdvancedModeDisabled = !isAdvancedModeEnabled;

export function AdvancedModeToggle() {
  const { mode, setMode } = useAppMode();
  const [enabled, setEnabled] = useState(!isAdvancedModeDisabled && mode === "advanced");
  const navigate = useNavigate();

  // Ensure UI reflects real mode and keep disabled state synced
  useEffect(() => {
    if (isAdvancedModeDisabled && mode === "advanced") {
      setMode("simple");
      setEnabled(false);
      return;
    }
    setEnabled(!isAdvancedModeDisabled && mode === "advanced");
  }, [isAdvancedModeDisabled, mode, setMode]);

  const handleToggle = (value: boolean) => {
    if (isAdvancedModeDisabled) {
      return;
    }
    setEnabled(value);
    setMode(value ? "advanced" : "simple");
    navigate("/");
  };

  return (
    <div
      className={`flex flex-row items-center gap-2 ${isAdvancedModeDisabled ? "opacity-60 cursor-not-allowed" : ""}`}
      aria-disabled={isAdvancedModeDisabled}
      title={isAdvancedModeDisabled ? "Advanced mode is temporarily unavailable" : undefined}
    >
      <span className="text-xs font-medium text-gray-300">Advanced</span>
      <Switch
        checked={enabled}
        onCheckedChange={isAdvancedModeDisabled ? undefined : handleToggle}
        disabled={isAdvancedModeDisabled}
        aria-disabled={isAdvancedModeDisabled}
      />
    </div>
  );
}
