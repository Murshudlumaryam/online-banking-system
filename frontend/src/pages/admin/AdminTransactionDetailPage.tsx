import { useState } from "react";
import type { FormEvent } from "react";
import { useParams } from "react-router";

import { useAdminTransaction, useReverseTransaction } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDateTime, formatMoney } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";

function ReverseTransactionForm({
  transactionId,
  onDone,
}: {
  transactionId: string;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const reverseTransaction = useReverseTransaction();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      await reverseTransaction.mutateAsync({ transactionId, reason });
      onDone();
    } catch {
      // Error surfaces inline below via mutation.error.
    }
  }

  return (
    <form
      className="mt-4 flex flex-col gap-3 rounded-md border border-brick-500/20 bg-brick-500/5 p-4"
      onSubmit={handleSubmit}
      noValidate
    >
      {reverseTransaction.isError && (
        <ErrorBanner message={getApiErrorMessage(reverseTransaction.error, "Couldn't reverse this transaction.")} />
      )}
      <p className="text-sm text-slate-600">
        This creates a new, opposite-direction transaction and marks the original as REVERSED. It
        cannot be undone.
      </p>
      <Input
        label="Reason"
        required
        placeholder="e.g. customer disputed this charge"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="flex gap-3">
        <Button type="submit" variant="danger" isLoading={reverseTransaction.isPending}>
          Confirm reversal
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function AdminTransactionDetailPage() {
  const { transactionId } = useParams<{ transactionId: string }>();
  const { data: txn, isLoading, isError, error } = useAdminTransaction(transactionId);
  const [isReversing, setIsReversing] = useState(false);

  if (isLoading) return <Spinner label="Loading transaction" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error, "Transaction not found.")} />;
  if (!txn) return null;

  const canReverse = txn.status === "SUCCESS";

  return (
    <div className="max-w-xl">
      <Card className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="font-mono text-lg text-ink">{txn.reference_number}</p>
            <p className="mt-1 text-sm text-slate-500">{formatDateTime(txn.created_at)}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {txn.transaction_type}
            </span>
            <Badge status={txn.status}>{txn.status}</Badge>
          </div>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Sender account</dt>
            <dd className="font-mono text-xs text-ink">
              {txn.sender_account_id ?? <span className="italic text-slate-400">External (outside this system)</span>}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Receiver account</dt>
            <dd className="font-mono text-xs text-ink">
              {txn.receiver_account_id ?? <span className="italic text-slate-400">External (outside this system)</span>}
            </dd>
          </div>
        </dl>

        {txn.note && <p className="mt-3 text-sm text-slate-500">Note: {txn.note}</p>}

        {txn.failure_reason && (
          <p className="mt-4 rounded-md bg-brick-500/5 px-3 py-2 text-sm text-brick-600">
            {txn.failure_reason}
          </p>
        )}

        <div className="mt-6">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Ledger</p>
          <ul className="mt-2">
            {txn.ledger_entries.map((entry) => (
              <li
                key={entry.id}
                className="flex items-center justify-between border-t border-slate-100 py-3 first:border-t-0"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      entry.entry_type === "DEBIT" ? "bg-brick-500" : "bg-forest-500"
                    }`}
                    aria-hidden
                  />
                  <span className="text-sm text-slate-600">
                    {entry.entry_type === "DEBIT" ? "Debit" : "Credit"}
                  </span>
                </div>
                <span
                  className={`font-mono tabular text-sm ${
                    entry.entry_type === "DEBIT" ? "text-brick-600" : "text-forest-600"
                  }`}
                >
                  {entry.entry_type === "DEBIT" ? "-" : "+"}
                  {formatMoney(entry.amount, entry.currency)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {canReverse && (
          <div className="mt-6 border-t border-slate-100 pt-6">
            {isReversing ? (
              <ReverseTransactionForm transactionId={txn.id} onDone={() => setIsReversing(false)} />
            ) : (
              <Button variant="danger" onClick={() => setIsReversing(true)}>
                Reverse this transaction
              </Button>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
