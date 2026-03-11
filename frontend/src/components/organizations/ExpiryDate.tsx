import { CardTitle } from "../ui/card";
import { differenceInDays, parseISO, format } from "date-fns";

type Org = {
  did: string;
  expiry: string;
};

export function ExpiryCard({ orgData, did }: { orgData: Org[]; did: string }) {
  const expiry = orgData.find((org) => org.did === did)?.expiry;
  if (!expiry) return null;

  const expiryDate = parseISO(expiry); // from "2025-09-20T18:53:23Z"
  const today = new Date();
  const daysLeft = differenceInDays(expiryDate, today);

  let label = "";
  if (daysLeft > 7) {
    label = `${daysLeft} days left`;
  } else if (daysLeft > 1) {
    label = `${daysLeft} days left`;
  } else if (daysLeft === 1) {
    label = "1 day left";
  } else if (daysLeft === 0) {
    label = "Expires today";
  } else {
    label = "Expired";
  }

  // highlight color
  let colorClass = "font-light";
  if (daysLeft <= 3 && daysLeft >= 0) {
    colorClass = "bg-red-200 text-red-800 font-light";
  } else if (daysLeft <= 7 && daysLeft > 3) {
    colorClass = "bg-yellow-200 text-yellow-800 font-light";
  }

  const formattedDate = format(expiryDate, "dd/MM/yy HH:mm");

  return (
    <CardTitle>
      Expires on:{" "}
      <span className={colorClass}>
        {formattedDate} ({label})
      </span>
    </CardTitle>
  );
}
