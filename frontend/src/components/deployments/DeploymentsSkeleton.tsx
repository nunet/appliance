"use client";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardHeader,
  CardDescription,
  CardTitle,
  CardFooter,
  CardAction,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";

export default function DeploymentDetailsSkeleton() {
  return (
    <>
      {/* Deployment Details Card */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card shadow-xs border rounded-lg">
          <CardHeader>
            <CardDescription>
              <Skeleton className="h-4 w-40" />
            </CardDescription>
            <CardTitle className="font-semibold tabular-nums @[250px]/card:text-xl">
              <Skeleton className="h-6 w-64" />
            </CardTitle>
          </CardHeader>
          <CardFooter className="flex-col items-start gap-2 text-sm">
            <div className="space-y-2 w-full">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-4 w-40" />
            </div>
            <Button
              disabled
              className="w-full lg:w-4/5 mx-auto block bg-red-500 text-white mt-3"
            >
              <Skeleton className="h-5 w-40 mx-auto" />
            </Button>
          </CardFooter>
        </Card>
      </div>

      {/* Status + Allocations */}
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 xl:grid-cols-3 lg:px-6 my-4">
        {/* Deployment Progress */}
        <Card className="@container/card lg:col-span-1">
          <CardHeader>
            <CardDescription>
              <Skeleton className="h-4 w-32" />
            </CardDescription>
            <CardTitle>
              <Skeleton className="h-6 w-20" />
            </CardTitle>
            <CardAction>
              <Skeleton className="h-6 w-6 rounded-full" />
            </CardAction>
          </CardHeader>
          <CardFooter>
            <div className="space-y-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-40" />
            </div>
          </CardFooter>
        </Card>

        {/* Allocations */}
        <Card className="@container/card lg:col-span-2">
          <CardHeader>
            <CardDescription>
              <Skeleton className="h-4 w-32" />
            </CardDescription>
            <Separator className="my-2" />
            <ul className="space-y-2">
              {Array.from({ length: 3 }).map((_, idx) => (
                <li key={idx} className="flex items-center gap-2">
                  <Skeleton className="h-4 w-48" />
                </li>
              ))}
            </ul>
          </CardHeader>
        </Card>
      </div>

      {/* Manifest */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card shadow-xs border rounded-lg">
          <CardHeader>
            <CardDescription>
              <Skeleton className="h-4 w-40" />
            </CardDescription>
            <Separator className="my-2" />
            <div className="bg-black/80 rounded-md p-3 h-64 overflow-hidden">
              <div className="space-y-2">
                {Array.from({ length: 10 }).map((_, idx) => (
                  <Skeleton
                    key={idx}
                    className="h-3 w-full bg-gray-600/40 rounded"
                  />
                ))}
              </div>
            </div>
          </CardHeader>
        </Card>
      </div>

      {/* Logs */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card shadow-xs border rounded-lg">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>
                <Skeleton className="h-4 w-40" />
              </CardDescription>
              <Button disabled variant="outline" size="sm">
                <Skeleton className="h-4 w-20" />
              </Button>
            </div>
            <Separator className="my-2" />
            <div className="bg-black/80 rounded-md p-3 h-64 overflow-hidden">
              <div className="space-y-2">
                {Array.from({ length: 12 }).map((_, idx) => (
                  <Skeleton
                    key={idx}
                    className="h-3 w-full bg-gray-600/40 rounded"
                  />
                ))}
              </div>
            </div>
          </CardHeader>
        </Card>
      </div>
    </>
  );
}
