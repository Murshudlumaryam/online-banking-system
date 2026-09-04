import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/apiClient";
import { authService } from "@/services/authService";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/Feedback";

const initialForm = {
  firstName: "",
  lastName: "",
  email: "",
  password: "",
  dateOfBirth: "",
  phoneNumber: "",
  address: "",
  nationalId: "",
};

function validatePassword(password: string): string | null {
  if (password.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(password)) return "Password must contain at least one uppercase letter.";
  if (!/\d/.test(password)) return "Password must contain at least one digit.";
  return null;
}

export function RegisterPage() {
  const { register, login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Once registration succeeds, the account exists but can't log in yet —
  // the flow moves to this screen instead of straight to the dashboard.
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);
  const [otpExpiresInSeconds, setOtpExpiresInSeconds] = useState(0);
  const [otpCode, setOtpCode] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    setSecondsLeft(otpExpiresInSeconds);
  }, [otpExpiresInSeconds]);

  useEffect(() => {
    if (!pendingUserId) return;
    const interval = setInterval(() => setSecondsLeft((prev) => Math.max(0, prev - 1)), 1000);
    return () => clearInterval(interval);
  }, [pendingUserId]);

  function updateField<K extends keyof typeof initialForm>(field: K, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const passwordError = validatePassword(form.password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await register({
        email: form.email,
        password: form.password,
        first_name: form.firstName,
        last_name: form.lastName,
        date_of_birth: form.dateOfBirth,
        phone_number: form.phoneNumber,
        address: form.address || undefined,
        national_id: form.nationalId,
      });
      setPendingUserId(result.id);
      setOtpExpiresInSeconds(result.otp_expires_in_seconds);
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't complete registration. Please check your details."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleConfirmOtp(event: FormEvent) {
    event.preventDefault();
    if (!pendingUserId || otpCode.length !== 6) return;
    setConfirmError(null);
    setIsConfirming(true);
    try {
      await authService.confirmRegistration(pendingUserId, otpCode);
      await login(form.email, form.password);
      navigate("/app/dashboard", { replace: true });
    } catch (err) {
      setConfirmError(getApiErrorMessage(err, "That code didn't work."));
    } finally {
      setIsConfirming(false);
    }
  }

  async function handleResend() {
    if (!pendingUserId) return;
    setConfirmError(null);
    setResendMessage(null);
    setIsResending(true);
    try {
      const result = await authService.resendRegistrationOtp(pendingUserId);
      setOtpExpiresInSeconds(result.otp_expires_in_seconds);
      setResendMessage("A new code is on its way.");
    } catch (err) {
      setConfirmError(getApiErrorMessage(err, "Couldn't resend the code."));
    } finally {
      setIsResending(false);
    }
  }

  if (pendingUserId) {
    const minutes = Math.floor(secondsLeft / 60);
    const seconds = secondsLeft % 60;
    const isExpired = secondsLeft <= 0;

    return (
      <AuthLayout title="Confirm your email" subtitle={`We sent a 6-digit code to ${form.email}`}>
        <form className="flex flex-col gap-4" onSubmit={handleConfirmOtp} noValidate>
          {confirmError && <ErrorBanner message={confirmError} />}
          {resendMessage && <p className="text-sm text-forest-600">{resendMessage}</p>}
          <Input
            label="Verification code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            hint={isExpired ? "This code has expired." : `Expires in ${minutes}:${seconds.toString().padStart(2, "0")}`}
            disabled={isExpired}
          />
          <button
            type="button"
            className="self-start text-sm font-medium text-ledger-600 underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
            onClick={() => void handleResend()}
            disabled={isResending || (!isExpired && secondsLeft > otpExpiresInSeconds - 30)}
          >
            {isResending ? "Sending a new code…" : "Didn't get a code? Resend"}
          </button>
          <Button type="submit" isLoading={isConfirming} className="w-full" disabled={otpCode.length !== 6 || isExpired}>
            Confirm and continue
          </Button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Open your account" subtitle="Takes about a minute">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="First name"
            required
            value={form.firstName}
            onChange={(e) => updateField("firstName", e.target.value)}
          />
          <Input
            label="Last name"
            required
            value={form.lastName}
            onChange={(e) => updateField("lastName", e.target.value)}
          />
        </div>
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={(e) => updateField("email", e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 8 characters, one uppercase letter, one digit."
          value={form.password}
          onChange={(e) => updateField("password", e.target.value)}
        />
        <Input
          label="Date of birth"
          type="date"
          required
          value={form.dateOfBirth}
          onChange={(e) => updateField("dateOfBirth", e.target.value)}
        />
        <Input
          label="Phone number"
          type="tel"
          required
          placeholder="+994501234567"
          value={form.phoneNumber}
          onChange={(e) => updateField("phoneNumber", e.target.value)}
        />
        <Input
          label="National ID"
          required
          hint="Your government-issued identity number (FIN/SSN or equivalent)."
          value={form.nationalId}
          onChange={(e) => updateField("nationalId", e.target.value)}
        />
        <Input
          label="Address (optional)"
          value={form.address}
          onChange={(e) => updateField("address", e.target.value)}
        />
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-ledger-700 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
