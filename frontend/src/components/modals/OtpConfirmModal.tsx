import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/Feedback";

interface OtpConfirmModalProps {
  referenceNumber: string;
  expiresInSeconds: number;
  isSubmitting: boolean;
  errorMessage: string | null;
  onConfirm: (otpCode: string) => void;
  onCancel: () => void;
  onResend?: () => void;
  isResending?: boolean;
  resendMessage?: string | null;
}

export function OtpConfirmModal({
  referenceNumber,
  expiresInSeconds,
  isSubmitting,
  errorMessage,
  onConfirm,
  onCancel,
  onResend,
  isResending = false,
  resendMessage = null,
}: OtpConfirmModalProps) {
  const [otpCode, setOtpCode] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(expiresInSeconds);

  useEffect(() => {
    setSecondsLeft(expiresInSeconds);
  }, [expiresInSeconds]);

  useEffect(() => {
    const interval = setInterval(() => {
      setSecondsLeft((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const isExpired = secondsLeft <= 0;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (otpCode.length === 6) onConfirm(otpCode);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
        <h2 className="font-display text-lg text-ink">Confirm your transfer</h2>
        <p className="mt-1 text-sm text-slate-500">
          Enter the 6-digit code sent to confirm transfer <span className="font-mono">{referenceNumber}</span>.
        </p>

        <form className="mt-5 flex flex-col gap-4" onSubmit={handleSubmit}>
          {errorMessage && <ErrorBanner message={errorMessage} />}
          {resendMessage && <p className="text-sm text-forest-600">{resendMessage}</p>}
          <Input
            label="One-time code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            hint={isExpired ? "This code has expired." : `Expires in ${minutes}:${seconds.toString().padStart(2, "0")}`}
            disabled={isExpired}
          />
          {onResend && (
            <button
              type="button"
              className="self-start text-sm font-medium text-ledger-600 underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
              onClick={onResend}
              disabled={isResending || (!isExpired && secondsLeft > expiresInSeconds - 30)}
            >
              {isResending ? "Sending a new code…" : "Didn't get a code? Resend"}
            </button>
          )}
          <div className="flex gap-3">
            <Button
              type="submit"
              className="flex-1"
              isLoading={isSubmitting}
              disabled={otpCode.length !== 6 || isExpired}
            >
              Confirm transfer
            </Button>
            <Button type="button" variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
