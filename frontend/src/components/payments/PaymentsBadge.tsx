import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Coins, Loader2 } from "lucide-react";
import { getPaymentsList } from "../../api/api";

const PAYMENTS_LIST_REFRESH_MS = 60 * 60 * 1000; // 1 hour

export function PaymentsBadge() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["payments", "list"],
    queryFn: getPaymentsList,
    staleTime: PAYMENTS_LIST_REFRESH_MS,
    gcTime: PAYMENTS_LIST_REFRESH_MS,
    refetchInterval: PAYMENTS_LIST_REFRESH_MS,
    refetchOnWindowFocus: false,
  });

  const unpaid = data?.unpaid_count ?? 0;

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="relative"
        onClick={() => navigate("/payments")}
        aria-label="Open payments"
        title="Payments"
      >
        {isLoading ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Coins className="h-5 w-5" />
        )}
        {!isError && unpaid > 0 && (
          <Badge
            variant="destructive"
            className="absolute -top-1 -right-1 h-5 w-5 p-0 flex items-center justify-center text-[10px] rounded-full"
          >
            {unpaid > 99 ? "99+" : unpaid}
          </Badge>
        )}
      </Button>
    </div>
  );
}
