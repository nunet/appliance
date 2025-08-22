import { useEffect, useState } from "react";
import axios from "axios";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card";
import { api } from "../../api/organizations";

const API_BASE = "YOUR_API_BASE_HERE";

/** Select organization */
export function OrgSelect({
  known,
  onSelect,
  disabled,
}: {
  known: Record<string, any>;
  onSelect: (did: string) => void;
  disabled?: boolean;
}) {
  const [joinedOrgs, setJoinedOrgs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchJoined = async () => {
      try {
        const data = await api.getJoinedOrgs();
        // Extract DIDs from response
        console.log("JOINED ORGS", data);
        setJoinedOrgs(data.map((org: any) => org.did));
      } catch (err) {
        console.error("Failed to fetch joined orgs", err);
      } finally {
        setLoading(false);
      }
    };
    fetchJoined();
  }, []);

  const orgEntries = Object.entries(known ?? {});

  const handleJoin = (did: string) => {
    onSelect(did); // trigger join flow
  };

  if (loading) return <div>Loading organizations...</div>;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Select Organization</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 gap-4">
            {orgEntries.map(([did, val]) => {
              console.log(did);
              console.log(joinedOrgs);
              const isJoined = joinedOrgs.includes(did);

              return (
                <div
                  key={did}
                  className={`relative p-4 rounded-2xl border transition-all duration-300 overflow-hidden
                    ${isJoined ? "border-green-500" : "border-gray-200"}
                  `}
                >
                  <div className="relative z-10 flex flex-col">
                    <span className="font-medium">{val?.name ?? did}</span>
                    <span className="text-xs opacity-70 mt-2" title={did}>
                      {"..." + did.slice(-20)}
                    </span>

                    <div className="mt-4 w-full">
                      {isJoined ? (
                        <span className="inline-block px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                          Joined
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => handleJoin(did)}
                          disabled={disabled}
                          className="w-full cursor-pointer"
                        >
                          Join
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
