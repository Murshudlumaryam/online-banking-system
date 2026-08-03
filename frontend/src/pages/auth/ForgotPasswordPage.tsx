import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";

import { authService } from "@/services/authService";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await authService.requestPasswordReset(email);
    } finally {
      // Always show the same confirmation, whether or not the email exists —
      // matches the backend's no-user-enumeration guarantee.
      setIsSubmitting(false);
      setSubmitted(true);
    }
  }

  if (submitted) {
    return (
      <AuthLayout title="Check your email">
        <p className="text-sm text-slate-600">
          If an account exists for <span className="font-medium text-ink">{email}</span>, we&apos;ve sent
          a link to reset your password.
        </p>
        <Link to="/login" className="mt-6 block text-center text-sm font-medium text-ledger-700 hover:underline">
          Back to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Reset your password" subtitle="We'll email you a reset link">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        <Input
          label="Email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          Send reset link
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
