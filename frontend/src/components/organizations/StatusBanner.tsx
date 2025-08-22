import { Progress } from "@radix-ui/react-progress";
import { CheckCircle2, AlertCircle, Shield, Badge, Mail } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card";
import type { StatusResponse } from "./OnboardFlow";

export function StatusBanner({ status }: { status?: StatusResponse }) {
  if (!status) return null;
  const { ui_state, ui_message, api_status, progress, current_step } = status;
  const emailHint = api_status === "email_sent";
  const isComplete = current_step === "complete";
  const isRejected = current_step === "rejected";

  return (
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
          <Badge variant="secondary" className="text-xs">
            API: {api_status ?? "n/a"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-sm text-muted-foreground">{ui_message}</div>
        {emailHint && (
          <div className="flex items-center gap-2 text-sm">
            <Mail className="w-4 h-4" />
            <span>We sent you an email — please verify.</span>
          </div>
        )}
        <Progress value={progress} />
      </CardContent>
    </Card>
  );
}
