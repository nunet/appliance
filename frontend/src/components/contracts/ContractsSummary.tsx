import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CalendarClock, CheckCircle2, Files, RefreshCw } from "lucide-react";

interface ContractsSummaryProps {
  incomingCount: number;
  signedCount: number;
  isLoading?: boolean;
  refreshing?: boolean;
  lastUpdatedLabel?: string | null;
  onRefresh?: () => void | Promise<void>;
}

interface SummaryCardProps {
  label: string;
  count: number;
  isLoading?: boolean;
  icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  accent?: "default" | "muted";
}

function SummaryCount({ count, isLoading }: { count: number; isLoading?: boolean }) {
  if (isLoading) {
    return <Skeleton className="h-10 w-16 rounded-md" />;
  }
  return <span className="text-3xl font-semibold">{count}</span>;
}

function SummaryCard({ label, count, isLoading, icon: Icon, accent = "default" }: SummaryCardProps) {
  return (
    <Card
      className={cn(
        "border-muted-foreground/20 bg-gradient-to-br",
        accent === "default"
          ? "from-background via-background to-muted/30"
          : "from-muted/60 via-background to-background"
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm text-muted-foreground font-medium">{label}</CardTitle>
        {Icon ? <Icon className="h-5 w-5 text-muted-foreground/70" /> : null}
      </CardHeader>
      <CardContent>
        <SummaryCount count={count} isLoading={isLoading} />
      </CardContent>
    </Card>
  );
}

export function ContractsSummary({
  incomingCount,
  signedCount,
  isLoading,
  refreshing,
  lastUpdatedLabel,
  onRefresh,
}: ContractsSummaryProps) {
  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold">Contracts</h1>
          <p className="text-muted-foreground text-sm">
            Track incoming contract requests, approvals, and signed agreements.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {lastUpdatedLabel ? (
            <Badge variant="outline" className="gap-1">
              <CalendarClock className="h-4 w-4" />
              Updated {lastUpdatedLabel}
            </Badge>
          ) : null}
          {onRefresh ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRefresh()}
              disabled={refreshing}
              className="gap-2"
            >
              <RefreshCw className={cn("h-4 w-4", refreshing ? "animate-spin" : undefined)} />
              Refresh
            </Button>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <SummaryCard
          label="Incoming contracts"
          count={incomingCount}
          isLoading={isLoading}
          icon={Files}
        />
        <SummaryCard
          label="Signed contracts"
          count={signedCount}
          isLoading={isLoading}
          icon={CheckCircle2}
          accent="muted"
        />
      </div>
    </div>
  );
}
