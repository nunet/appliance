import { Button } from "../ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";

/** Show joined orgs as cards */
export function OrgCards({ orgs }: { orgs: Record<string, any> }) {
  if (!orgs || Object.keys(orgs).length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        You haven’t joined any organizations yet.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Object.entries(orgs).map(([key, val]) => (
        <Card key={key} className="flex flex-col">
          <CardHeader>
            <CardTitle>{val?.name ?? key}</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 text-sm space-y-2">
            <div className="font-mono text-xs break-all">{key}</div>
            {val?.description && (
              <div className="text-muted-foreground">{val.description}</div>
            )}
          </CardContent>
          <CardFooter>
            <Button className="w-full">Open</Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}
