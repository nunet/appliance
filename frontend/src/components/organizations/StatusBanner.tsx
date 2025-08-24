"use client";

import { motion } from "framer-motion";
import { Progress } from "@radix-ui/react-progress";
import { CheckCircle2, AlertCircle, Shield, Mail } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card";
import type { StatusResponse } from "./OnboardFlow";

export function StatusBanner({ status }: { status?: StatusResponse }) {
  if (!status) return null;

  const { ui_state, ui_message, api_status, progress, current_step } = status;

  const emailHint = api_status === "email_sent";
  const isComplete = current_step === "complete";
  const isRejected = current_step === "rejected";
  const isImportant = isComplete || isRejected || emailHint || ui_state === "error"; // add more conditions if needed

  // hide if it's not an important step
  if (!isImportant) return null;

  return (
    <div className="rounded-xl shadow-sm">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isComplete ? (
                <CheckCircle2 className="w-5 h-5 text-green-600" />
              ) : isRejected ? (
                <AlertCircle className="w-5 h-5 text-red-600" />
              ) : (
                <Shield className="w-5 h-5" />
              )}
              <CardTitle className="capitalize">
                {ui_state.replaceAll("_", " ")}
              </CardTitle>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-muted-foreground break-all whitespace-pre-wrap">{ui_message}</div>
          {emailHint && (
            <div className="flex items-center gap-2 text-sm text-blue-600 font-medium">
              <Mail className="w-4 h-4" />
              <span>We sent you an email — please verify.</span>
            </div>
          )}
          <Progress value={progress} />
        </CardContent>
      </Card>
    </div>
  );
}
