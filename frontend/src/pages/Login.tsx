import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAuth } from "../hooks/useAuth";
import { toast } from "sonner";

export default function LoginPage() {
  const { login } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = (location.state as { from?: { pathname?: string } })?.from?.pathname ?? "/";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await login(password);
      setPassword("");
      toast.success("Signed in");
      navigate(redirectTo, { replace: true });
    } catch (error) {
      console.error("Login failed", error);
      toast.error("Invalid password");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/15 via-background to-background px-4 py-10">
      <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute left-1/2 top-0 h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-primary/20 opacity-70 blur-3xl sm:h-[540px] sm:w-[540px]" aria-hidden />
        <div className="absolute bottom-[-20%] right-[-10%] h-64 w-64 rounded-full bg-primary/10 opacity-60 blur-3xl sm:bottom-[-10%] sm:right-[-5%]" aria-hidden />
      </div>
      <Card className="relative w-full max-w-md border border-primary/20 bg-background/95 shadow-2xl backdrop-blur">
        <CardHeader className="flex flex-col items-center gap-4 text-center">
          <img
            src="/nunet-appliance-logo-white.png"
            alt="NuNet Appliance logo"
            className="h-48 w-auto max-w-[240px] object-contain drop-shadow-2xl sm:h-60"
          />
          <div className="space-y-2">
            <CardTitle className="text-3xl font-semibold tracking-tight">Welcome back</CardTitle>
            <CardDescription className="text-base text-muted-foreground">
              Enter the admin password to manage your NuNet appliance.
            </CardDescription>
          </div>
        </CardHeader>
        <form onSubmit={handleSubmit} data-testid="login-form">
          <CardContent className="space-y-6 pb-0">
            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-medium text-foreground">
                Admin password
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                className="h-12 text-base shadow-sm"
                required
                data-testid="login-password-input"
              />
            </div>
          </CardContent>
          <CardFooter className="flex-col items-stretch gap-4 px-6 pb-6 pt-6">
            <Button
              className="w-full py-6 text-base font-semibold shadow-lg shadow-primary/20 transition-all hover:shadow-2xl focus-visible:ring-primary/40"
              size="lg"
              type="submit"
              disabled={submitting || password.length === 0}
              data-testid="login-submit-button"
            >
              {submitting ? "Signing in..." : "Sign in"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}

