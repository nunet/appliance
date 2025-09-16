import { Skeleton } from "../../components/ui/skeleton";
import { Card, CardHeader, CardContent } from "../../components/ui/card";

export function SectionCardsSkeleton() {
  return (
    <>
      {/* Top Full-Width Card */}
      <div className="grid grid-cols-1 gap-4 px-4">
        <Card className="p-4">
          <CardHeader>
            <Skeleton className="h-4 w-24" /> {/* DID Key Label */}
            <Skeleton className="h-8 w-64 mt-2" /> {/* DID Value */}
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-4 w-40" /> {/* Version */}
            <Skeleton className="h-4 w-56" /> {/* Peer ID */}
            <div className="flex gap-2 mt-2">
              <Skeleton className="h-6 w-20 rounded-md" />
              <Skeleton className="h-6 w-20 rounded-md" />
              <Skeleton className="h-6 w-20 rounded-md" />
              <Skeleton className="h-6 w-20 rounded-md" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Middle Row - 3 Cards */}
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-2 xl:grid-cols-3 lg:px-6 mt-4">
        {[...Array(3)].map((_, i) => (
          <Card key={i} className="p-4">
            <CardHeader>
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-32 mt-2" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-32" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-32" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Bottom Row - 3 Cards */}
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-2 xl:grid-cols-3 lg:px-6 mt-4">
        {[...Array(3)].map((_, i) => (
          <Card key={i} className="p-4">
            <CardHeader>
              <Skeleton className="h-4 w-32" />
              <div className="space-y-2 mt-3">
                <Skeleton className="h-4 w-64" />
                <Skeleton className="h-4 w-56" />
                <Skeleton className="h-4 w-48" />
              </div>
            </CardHeader>
          </Card>
        ))}
      </div>
    </>
  );
}
