import { useEffect, useState } from "react";
import axios from "axios";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card";
import { api } from "../../api/organizations";
import { Circle } from "lucide-react";
import { ExpiryCard } from "./ExpiryDate";


/** Select organization */
export function OrgSelect({
  known,
  onSelect,
  disabled,
  setStartOperation,
}: {
  known: Record<string, any>;
  onSelect: (did: string) => void;
  disabled?: boolean;
  setStartOperation: (val: boolean) => void;
}) {
  const [joinedOrgs, setJoinedOrgs] = useState<any>([]);
  const [orgData, setOrgData] = useState<any>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchJoined = async () => {
      try {
        const data = await api.getJoinedOrgs();
        // Extract DIDs from response
        console.log("JOINED ORGS", data);
        setJoinedOrgs(data.map((org: any) => org.did));
        setOrgData(data);
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
    setStartOperation(true);
  };

  if (loading) return <div>Loading organizations...</div>;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Select Organization</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 gap-4 items-start">
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
                    <div className="flex flex-row justify-between items-center">
                      <span className="font-medium">{val?.name ?? did}</span>
                      {isJoined && (
                        <span className="inline-block px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                          Joined
                        </span>
                      )}
                    </div>

                    <span className="text-xs opacity-70 mt-2" title={did}>
                      {"..." + did.slice(-20)}
                    </span>
                    {isJoined && (
                      <>
                        <Card className="flex flex-col mt-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-muted/30 gap-3">
                          <CardTitle>Capabilities:</CardTitle>
                          <CardContent>
                            {orgData
                              .filter((org) => org.did === did)[0]
                              .capabilities.map((c) => (
                                <p className="flex flex-row align-middle items-center gap-3">
                                  <Circle className="" size={10} />
                                  {c}
                                </p>
                              ))}
                          </CardContent>
                        </Card>
                        <Card className="flex flex- mt-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-muted/30 gap-3">
                          <ExpiryCard orgData={orgData} did={did} />
                        </Card>
                      </>
                    )}
                    <div className="mt-4 w-full">
                      {!isJoined && (
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
