import { Link } from "react-router-dom";

import { useAccounts } from "@/hooks/useAccounts";
import { formatAccountNumber, formatMoney } from "@/lib/format";
import { getApiErrorMessage } from "@/lib/apiClient";
import { Badge } from "@/components/ui/Badge";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";

export function AccountsPage() {
  const { data: accounts, isLoading, isError, error } = useAccounts();

  if (isLoading) return <Spinner label="Loading accounts" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  return (
    <Card>
      {!accounts || accounts.length === 0 ? (
        <EmptyState title="No accounts yet" description="Contact support to open your first account." />
      ) : (
        <ul className="divide-y divide-slate-100">
          {accounts.map((account) => (
            <li key={account.id}>
              <Link
                to={`/app/accounts/${account.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
              >
                <div>
                  <p className="font-mono text-sm text-ink">{formatAccountNumber(account.account_number)}</p>
                  <p className="text-xs text-slate-500">
                    {account.account_type} &middot; {account.currency}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono tabular text-sm text-ink">
                    {formatMoney(account.balance, account.currency)}
                  </span>
                  <Badge status={account.status}>{account.status}</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
