import { useState } from "react";
import { Link } from "react-router";

import { useAdminTransactions } from "@/hooks/useAdmin";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDateTime, formatMoney } from "@/lib/format";
import type { TransactionStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";

const STATUS_OPTIONS: TransactionStatus[] = ["PENDING", "SUCCESS", "FAILED", "REVERSED"];

export function AdminTransactionsPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<TransactionStatus | "">("");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput);
  const { data, isLoading, isError, error } = useAdminTransactions(
    page,
    statusFilter || undefined,
    search || undefined,
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="max-w-sm flex-1">
          <Input
            label="Search"
            placeholder="Reference number (e.g. TXN-...)"
            value={searchInput}
            onChange={(e) => {
              setSearchInput(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="max-w-xs">
          <Select
            label="Filter by status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as TransactionStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {isLoading ? (
        <Spinner label="Loading transactions" />
      ) : isError ? (
        <ErrorBanner message={getApiErrorMessage(error)} />
      ) : (
        <Card>
          {!data || data.items.length === 0 ? (
            <EmptyState title="No transactions found" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.items.map((txn) => (
                <li key={txn.id}>
                  <Link
                    to={`/admin/transactions/${txn.id}`}
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
          {data && (
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
          )}
        </Card>
      )}
    </div>
  );
}
