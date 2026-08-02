import { Link, useParams } from "react-router-dom";

import { useAccount } from "@/hooks/useAccounts";
import { formatAccountNumber, formatMoney } from "@/lib/format";
import { getApiErrorMessage } from "@/lib/apiClient";
import { Badge } from "@/components/ui/Badge";
import { Card, ErrorBanner, Spinner } from "@/components/ui/Feedback";

export function AccountDetailPage() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data: account, isLoading, isError, error } = useAccount(accountId);

  if (isLoading) return <Spinner label="Loading account" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error, "Account not found.")} />;
  if (!account) return null;

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <Card className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {account.account_type} &middot; {account.currency}
            </p>
            <p className="mt-1 font-mono text-lg text-ink">{formatAccountNumber(account.account_number)}</p>
          </div>
          <Badge status={account.status}>{account.status}</Badge>
        </div>
        <p className="mt-6 text-xs font-medium uppercase tracking-wide text-slate-500">Balance</p>
        <p className="font-mono text-3xl tabular text-ledger-800">
          {formatMoney(account.balance, account.currency)}
        </p>
      </Card>

      <div className="flex gap-3">
        <Link
          to="/app/transfer"
          className="inline-flex items-center justify-center rounded-md bg-ledger-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-ledger-800"
        >
          Transfer from this account
        </Link>
        <Link
          to="/app/transactions"
          className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-ledger-700 hover:bg-slate-50"
        >
          View transaction history
        </Link>
      </div>
    </div>
  );
}
