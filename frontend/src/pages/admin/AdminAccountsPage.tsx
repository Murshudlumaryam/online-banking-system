import { useState } from "react";

import { useAdminAccounts, useCreateCard, useDepositToAccount, useUpdateAccountStatus, useWithdrawFromAccount } from "@/hooks/useAdmin";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatAccountNumber, formatMoney } from "@/lib/format";
import type { AccountResponse, AccountStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { DepositWithdrawalModal } from "@/components/modals/DepositWithdrawalModal";

const STATUS_OPTIONS: AccountStatus[] = ["ACTIVE", "BLOCKED", "CLOSED", "PENDING"];

export function AdminAccountsPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<AccountStatus | "">("");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput);
  const { data, isLoading, isError, error } = useAdminAccounts(page, statusFilter || undefined, search || undefined);
  const updateStatus = useUpdateAccountStatus();
  const createCard = useCreateCard();
  const depositMutation = useDepositToAccount();
  const withdrawMutation = useWithdrawFromAccount();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [cashModal, setCashModal] = useState<{ mode: "deposit" | "withdraw"; account: AccountResponse } | null>(null);

  async function handleIssueCard(accountId: string) {
    setFeedback(null);
    try {
      const card = await createCard.mutateAsync({ account_id: accountId, card_type: "DEBIT" });
      setFeedback(`Card ${card.masked_card_number} issued.`);
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't issue a card."));
    }
  }

  async function handleCashOperation(amount: string, note: string) {
    if (!cashModal) return;
    const { mode, account } = cashModal;
    const mutation = mode === "deposit" ? depositMutation : withdrawMutation;
    try {
      await mutation.mutateAsync({
        accountId: account.id,
        payload: { amount, currency: account.currency, note: note || undefined },
      });
      setFeedback(`${mode === "deposit" ? "Deposited" : "Withdrew"} ${amount} ${account.currency}.`);
      setCashModal(null);
    } catch {
      // Error surfaces inline in the modal via mutation.error — keep it open.
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="max-w-sm flex-1">
          <Input
            label="Search"
            placeholder="Account number"
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
                    {account.customer_name && (
                      <p className="text-sm font-medium text-ink">{account.customer_name}</p>
                    )}
                    <p className="font-mono text-sm text-slate-600">{formatAccountNumber(account.account_number)}</p>
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
                    <Button size="sm" variant="secondary" onClick={() => setCashModal({ mode: "deposit", account })}>
                      Deposit
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setCashModal({ mode: "withdraw", account })}>
                      Withdraw
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

      {cashModal && (
        <DepositWithdrawalModal
          mode={cashModal.mode}
          accountNumber={formatAccountNumber(cashModal.account.account_number)}
          currency={cashModal.account.currency}
          isSubmitting={depositMutation.isPending || withdrawMutation.isPending}
          errorMessage={
            depositMutation.error
              ? getApiErrorMessage(depositMutation.error, "Couldn't complete the deposit.")
              : withdrawMutation.error
                ? getApiErrorMessage(withdrawMutation.error, "Couldn't complete the withdrawal.")
                : null
          }
          onSubmit={handleCashOperation}
          onCancel={() => setCashModal(null)}
        />
      )}
    </div>
  );
}
