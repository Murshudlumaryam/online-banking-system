import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { getApiErrorMessage } from "@/lib/apiClient";
import { authService } from "@/services/authService";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/Feedback";

export function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setError("This reset link is missing its token. Please request a new one.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await authService.confirmPasswordReset(token, newPassword);
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (err) {
      setError(getApiErrorMessage(err, "This reset link is invalid or has expired."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Choose a new password">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 8 characters, one uppercase letter, one digit."
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          Update password
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        <Link to="/login" className="font-medium text-ledger-700 hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
