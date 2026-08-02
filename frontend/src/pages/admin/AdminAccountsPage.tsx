import { useState } from "react";

import { useAdminAccounts, useCreateCard, useUpdateAccountStatus } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatAccountNumber, formatMoney } from "@/lib/format";
import type { AccountStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";

const STATUS_OPTIONS: AccountStatus[] = ["ACTIVE", "BLOCKED", "CLOSED", "PENDING"];

export function AdminAccountsPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<AccountStatus | "">("");
  const { data, isLoading, isError, error } = useAdminAccounts(page, statusFilter || undefined);
  const updateStatus = useUpdateAccountStatus();
  const createCard = useCreateCard();
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleIssueCard(accountId: string) {
    setFeedback(null);
    try {
      const card = await createCard.mutateAsync({ account_id: accountId, card_type: "DEBIT" });
      setFeedback(`Card ${card.masked_card_number} issued.`);
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't issue a card."));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-xs">
        <Select
          label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as AccountStatus | "");
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

      {feedback && <p className="text-sm text-slate-600">{feedback}</p>}

      {isLoading ? (
        <Spinner label="Loading accounts" />
      ) : isError ? (
        <ErrorBanner message={getApiErrorMessage(error)} />
      ) : (
        <Card>
          {!data || data.items.length === 0 ? (
            <EmptyState title="No accounts found" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.items.map((account) => (
                <li key={account.id} className="flex items-center justify-between px-5 py-4">
                  <div>
                    <p className="font-mono text-sm text-ink">{formatAccountNumber(account.account_number)}</p>
                    <p className="text-xs text-slate-500">
                      {account.account_type} &middot; {formatMoney(account.balance, account.currency)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge status={account.status}>{account.status}</Badge>
                    <select
                      className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                      value={account.status}
                      onChange={(e) =>
                        updateStatus.mutate({ accountId: account.id, status: e.target.value as AccountStatus })
                      }
                    >
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                    <Button size="sm" variant="secondary" onClick={() => handleIssueCard(account.id)} isLoading={createCard.isPending}>
                      Issue card
                    </Button>
                  </div>
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
