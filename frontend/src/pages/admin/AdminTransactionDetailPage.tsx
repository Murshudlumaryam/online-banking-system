import { useParams } from "react-router";

import { useAdminTransaction } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDateTime, formatMoney } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { Card, ErrorBanner, Spinner } from "@/components/ui/Feedback";

export function AdminTransactionDetailPage() {
  const { transactionId } = useParams<{ transactionId: string }>();
  const { data: txn, isLoading, isError, error } = useAdminTransaction(transactionId);

  if (isLoading) return <Spinner label="Loading transaction" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error, "Transaction not found.")} />;
  if (!txn) return null;

  return (
    <div className="max-w-xl">
      <Card className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="font-mono text-lg text-ink">{txn.reference_number}</p>
            <p className="mt-1 text-sm text-slate-500">{formatDateTime(txn.created_at)}</p>
          </div>
          <Badge status={txn.status}>{txn.status}</Badge>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Sender account</dt>
            <dd className="font-mono text-xs text-ink">{txn.sender_account_id}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Receiver account</dt>
            <dd className="font-mono text-xs text-ink">{txn.receiver_account_id}</dd>
          </div>
        </dl>

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
      </Card>
    </div>
  );
}
