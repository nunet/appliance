// pages/NotFound.tsx
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-screen text-center px-6">
      <h1 className="text-8xl font-bold">404</h1>
      <p className="mt-4 text-xl">
        Oops! The page you're looking for doesn’t exist.
      </p>
      <div className="mt-6">
        <Button
          variant="default"
          onClick={() => navigate("/")}
          className="px-6 py-3 text-lg"
        >
          Go Back Home
        </Button>
      </div>
    </div>
  );
}
