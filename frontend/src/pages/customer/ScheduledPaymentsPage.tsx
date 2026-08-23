import { useState } from "react";
import type { FormEvent } from "react";

import { useAccounts } from "@/hooks/useAccounts";
import {
  useCancelScheduledPayment,
  useCreateScheduledPayment,
  useScheduledPayments,
} from "@/hooks/useScheduledPayments";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatDateTime } from "@/lib/format";
import type { ScheduledPaymentResponse } from "@/services/scheduledPaymentsService";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";

const FREQUENCIES = [
  { value: "DAILY", label: "Daily" },
  { value: "WEEKLY", label: "Weekly" },
  { value: "MONTHLY", label: "Monthly" },
] as const;

function CreateScheduledPaymentForm({ onDone }: { onDone: () => void }) {
  const { data: accounts } = useAccounts();
  const [senderAccountId, setSenderAccountId] = useState("");
  const [receiverAccountNumber, setReceiverAccountNumber] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("AZN");
  const [frequency, setFrequency] = useState<(typeof FREQUENCIES)[number]["value"]>("MONTHLY");
  const [error, setError] = useState<string | null>(null);
  const createScheduledPayment = useCreateScheduledPayment();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createScheduledPayment.mutateAsync({
        sender_account_id: senderAccountId,
        receiver_account_number: receiverAccountNumber.trim(),
        amount,
        currency,
        frequency,
      });
      onDone();
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't set up this scheduled payment."));
    }
  }

  return (
    <Card className="p-6">
      <h3 className="font-display text-lg text-ink">New scheduled payment</h3>
      <form className="mt-4 flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <ErrorBanner message={error} />}

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">From account</span>
          <select
            required
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={senderAccountId}
            onChange={(e) => setSenderAccountId(e.target.value)}
          >
            <option value="" disabled>
              Select an account
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_number} — {formatMoney(account.balance, account.currency)}
              </option>
            ))}
          </select>
        </label>

        <Input
          label="Receiver account number"
          required
          value={receiverAccountNumber}
          onChange={(e) => setReceiverAccountNumber(e.target.value)}
        />

        <div className="grid grid-cols-2 gap-4">
          <Input
            label={`Amount (${currency})`}
            required
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <Input
            label="Currency"
            required
            maxLength={3}
            value={currency}
            onChange={(e) => setCurrency(e.target.value.toUpperCase())}
          />
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Repeats</span>
          <select
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value as typeof frequency)}
          >
            {FREQUENCIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>

        <div className="flex gap-3">
          <Button type="submit" isLoading={createScheduledPayment.isPending}>
            Create scheduled payment
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ScheduledPaymentRow({ payment }: { payment: ScheduledPaymentResponse }) {
  const cancelScheduledPayment = useCancelScheduledPayment();

  return (
    <li className="flex items-center justify-between gap-4 px-5 py-4">
      <div>
        <p className="text-sm font-medium text-ink">
          {formatMoney(payment.amount, payment.currency)} · {payment.frequency.toLowerCase()}
        </p>
        <p className="font-mono text-xs text-slate-500">To {payment.receiver_account_number}</p>
        <p className="mt-1 text-xs text-slate-400">
          {payment.is_active ? `Next run: ${formatDateTime(payment.next_run_at)}` : "Cancelled"}
        </p>
        {payment.last_failure_reason && (
          <p className="mt-1 text-xs text-red-500">Last attempt failed: {payment.last_failure_reason}</p>
        )}
      </div>
      {payment.is_active && (
        <Button
          size="sm"
          variant="danger"
          isLoading={cancelScheduledPayment.isPending}
          onClick={() => cancelScheduledPayment.mutate(payment.id)}
        >
          Cancel
        </Button>
      )}
    </li>
  );
}

export function ScheduledPaymentsPage() {
  const { data: payments, isLoading, isError, error } = useScheduledPayments();
  const [isAdding, setIsAdding] = useState(false);

  if (isLoading) return <Spinner label="Loading scheduled payments" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl text-ink">Scheduled payments</h1>
        <p className="mt-1 text-sm text-slate-500">
          Set up a transfer to repeat automatically — daily, weekly, or monthly.
        </p>
      </div>

      {isAdding ? (
        <CreateScheduledPaymentForm onDone={() => setIsAdding(false)} />
      ) : (
        <div>
          <Button onClick={() => setIsAdding(true)}>New scheduled payment</Button>
        </div>
      )}

      <Card>
        {!payments || payments.length === 0 ? (
          <EmptyState
            title="No scheduled payments"
            description="Set up a recurring transfer — like a monthly rent payment — and it will run automatically."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {payments.map((p) => (
              <ScheduledPaymentRow key={p.id} payment={p} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
