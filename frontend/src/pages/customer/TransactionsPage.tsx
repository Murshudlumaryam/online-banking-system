import { useState } from "react";
import { Link } from "@/lib/router";

import { useTransactions } from "@/hooks/useTransactions";
import { formatDateTime, formatMoney } from "@/lib/format";
import { getApiErrorMessage } from "@/lib/apiClient";
import { Badge } from "@/components/ui/Badge";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";

export function TransactionsPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error } = useTransactions(page);

  if (isLoading) return <Spinner label="Loading transactions" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;
  if (!data) return null;

  return (
    <Card>
      {data.items.length === 0 ? (
        <EmptyState title="No transactions yet" description="Your transfers will show up here." />
      ) : (
        <ul className="divide-y divide-slate-100">
          {data.items.map((txn) => (
            <li key={txn.id}>
              <Link
                to={`/app/transactions/${txn.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
              >
                <div>
                  <p className="font-mono text-sm text-ink">{txn.reference_number}</p>
                  <p className="text-xs text-slate-500">{formatDateTime(txn.created_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono tabular text-sm text-ink">
                    {formatMoney(txn.amount, txn.currency)}
                  </span>
                  <Badge status={txn.status}>{txn.status}</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
    </Card>
  );
}
