import { FormEvent, useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAuth } from "../hooks/useAuth";
import { toast } from "sonner";

export default function SetupAdmin() {
  const { setupPassword } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setupToken, setSetupToken] = useState<string | null>(null);
  const [resetToken, setResetToken] = useState<string | null>(null);

  // Extract tokens from URL query parameters
  // Note: HashRouter puts query params in the hash, but we also check window.location.search
  // for backward compatibility with URLs that have tokens before the hash
  useEffect(() => {
    // First try to get from hash router's searchParams (e.g., #/setup?setup_token=...)
    let setup = searchParams.get("setup_token");
    let reset = searchParams.get("reset_token");
    
    // Fallback: check window.location.search for tokens before the hash (backward compatibility)
    // This handles URLs like https://192.168.88.168:8443?setup_token=...#/setup
    if (!setup && !reset) {
      const rootParams = new URLSearchParams(window.location.search);
      setup = rootParams.get("setup_token") || setup;
      reset = rootParams.get("reset_token") || reset;
    }
    
    setSetupToken(setup);
    setResetToken(reset);
    
    // Show error if no token is provided
    if (!setup && !reset) {
      setError("Setup token or reset token is required. Please access this page from the boot splash screen.");
    }
  }, [searchParams]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    if (!setupToken && !resetToken) {
      setError("Setup token or reset token is required. Please access this page from the boot splash screen.");
      return;
    }

    setSubmitting(true);
    try {
      await setupPassword(password, setupToken || undefined, resetToken || undefined);
      toast.success("Admin password set");
      navigate("/", { replace: true });
    } catch (err: any) {
      console.error("Failed to configure password", err);
      const errorMessage = err?.response?.data?.detail || "Could not save password. Please try again.";
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Secure your appliance</CardTitle>
          <CardDescription>
            {setupToken 
              ? "First boot setup: Choose a strong admin password. You will use this password to access the web manager."
              : resetToken
              ? "Password reset: Choose a new admin password. You will use this password to access the web manager."
              : "Choose a strong admin password. You will use this password to access the web manager."}
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password">New admin password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                autoComplete="new-password"
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm">Confirm password</Label>
              <Input
                id="confirm"
                type="password"
                value={confirm}
                autoComplete="new-password"
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
          <CardFooter>
            <Button className="w-full" type="submit" disabled={submitting}>
              {submitting ? "Saving..." : "Set password"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
