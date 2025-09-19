import { FormEvent, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAuth } from "../hooks/useAuth";
import { toast } from "sonner";

export default function SetupAdmin() {
  const { setupPassword } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const setupToken = useMemo(() => {
    const directParams = new URLSearchParams(window.location.search);
    const directToken = directParams.get("setup_token");
    if (directToken) {
      return directToken;
    }
    const hash = window.location.hash;
    const hashQueryIndex = hash.indexOf("?");
    if (hashQueryIndex !== -1) {
      const hashParams = new URLSearchParams(hash.substring(hashQueryIndex + 1));
      const hashToken = hashParams.get("setup_token");
      if (hashToken) {
        return hashToken;
      }
    }
    return "";
  }, [location.hash, location.search]);
  const hasToken = setupToken.length > 0;
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

    if (!hasToken) {
      setError("Missing setup token. Use the QR code shown on the appliance terminal to access this page.");
      return;
    }

    setSubmitting(true);
    try {
      await setupPassword(password, setupToken);
      toast.success("Admin password set");
      navigate("/", { replace: true });
    } catch (err) {
      console.error("Failed to configure password", err);
      setError("Could not save password. Verify the setup token and try again.");
      toast.error("Could not save password. Please try again.");
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
            Choose a strong admin password. You will use this password to access the web manager.
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
            {!hasToken && (
              <p className="text-sm text-destructive">
                Missing setup token. Use the appliance terminal QR code to access this page.
              </p>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
          <CardFooter>
            <Button className="w-full" type="submit" disabled={submitting || !hasToken}>
              {submitting ? "Saving..." : "Set password"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
