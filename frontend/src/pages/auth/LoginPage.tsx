import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/apiClient";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/Feedback";

export function LoginPage() {
  const { login, completeMfaLogin, role } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  function goToLandingPage() {
    const from = (location.state as { from?: Location })?.from?.pathname;
    navigate(from ?? (role === "ADMIN" ? "/admin/customers" : "/app/dashboard"), { replace: true });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.mfaRequired && result.challengeToken) {
        setChallengeToken(result.challengeToken);
      } else {
        goToLandingPage();
      }
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't sign you in. Check your email and password."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleMfaSubmit(event: FormEvent) {
    event.preventDefault();
    if (!challengeToken) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await completeMfaLogin(challengeToken, mfaCode);
      goToLandingPage();
    } catch (err) {
      setError(getApiErrorMessage(err, "That code didn't work. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (challengeToken) {
    return (
      <AuthLayout title="Enter your authenticator code" subtitle="Two-factor authentication is enabled on this account">
        <form className="flex flex-col gap-4" onSubmit={handleMfaSubmit} noValidate>
          {error && <ErrorBanner message={error} />}
          <Input
            label="6-digit code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            maxLength={6}
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <Button type="submit" isLoading={isSubmitting} disabled={mfaCode.length !== 6} className="w-full">
            Verify and sign in
          </Button>
          <button
            type="button"
            className="text-center text-sm text-slate-500 hover:underline"
            onClick={() => {
              setChallengeToken(null);
              setMfaCode("");
              setError(null);
            }}
          >
            Back to sign in
          </button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Sign in to your account">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm text-ledger-700 hover:underline">
            Forgot your password?
          </Link>
        </div>
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        Don&apos;t have an account?{" "}
        <Link to="/register" className="font-medium text-ledger-700 hover:underline">
          Open one
        </Link>
      </p>
    </AuthLayout>
  );
}
