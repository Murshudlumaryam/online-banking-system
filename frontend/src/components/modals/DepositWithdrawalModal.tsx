import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";

interface DepositWithdrawalModalProps {
  mode: "deposit" | "withdraw";
  accountNumber: string;
  currency: string;
  isSubmitting: boolean;
  errorMessage: string | null;
  onSubmit: (amount: string, note: string) => void;
  onCancel: () => void;
}

export function DepositWithdrawalModal({
  mode,
  accountNumber,
  currency,
  isSubmitting,
  errorMessage,
  onSubmit,
  onCancel,
}: DepositWithdrawalModalProps) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");

  const isDeposit = mode === "deposit";
  const title = isDeposit ? "Deposit funds" : "Withdraw funds";
  const actionLabel = isDeposit ? "Deposit" : "Withdraw";
  const isValidAmount = /^\d+(\.\d{1,2})?$/.test(amount) && Number(amount) > 0;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (isValidAmount) onSubmit(amount, note);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
        <h2 className="font-display text-lg text-ink">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">
          {isDeposit ? "Credit" : "Debit"} account <span className="font-mono">{accountNumber}</span>. This
          represents cash handled at a branch, not a self-service customer action.
        </p>

        <form className="mt-5 flex flex-col gap-4" onSubmit={handleSubmit}>
          {errorMessage && <ErrorBanner message={errorMessage} />}
          <Input
            label={`Amount (${currency})`}
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
            placeholder="0.00"
            autoFocus
          />
          <Input
            label="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={isDeposit ? "e.g. Cash deposit at branch" : "e.g. ATM withdrawal"}
            maxLength={500}
          />
          <div className="flex gap-3">
            <Button type="submit" className="flex-1" isLoading={isSubmitting} disabled={!isValidAmount}>
              {actionLabel}
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
