import { Link } from "react-router";

import { useDashboard } from "@/hooks/useCustomerProfile";
import { formatMoney, formatAccountNumber } from "@/lib/format";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Badge } from "@/components/ui/Badge";
import { getApiErrorMessage } from "@/lib/apiClient";

export function DashboardPage() {
  const { data, isLoading, isError, error } = useDashboard();

  if (isLoading) return <Spinner label="Loading your dashboard" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="text-sm text-slate-500">Welcome back,</p>
        <h2 className="font-display text-2xl text-ink">{data.full_name}</h2>
        <p className="mt-1 text-sm text-slate-500">Customer No. {data.customer_number}</p>
      </div>

      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Total balance
        </h3>
        {data.balances_by_currency.length === 0 ? (
          <Card className="p-6">
            <EmptyState
              title="No funded accounts yet"
              description="Once an account is opened for you, your balance will appear here."
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.balances_by_currency.map((balance) => (
              <Card key={balance.currency} className="p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {balance.currency}
                </p>
                <p className="mt-2 font-mono text-2xl tabular text-ledger-800">
                  {formatMoney(balance.total_balance, balance.currency)}
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="flex gap-3">
        <Link
          to="/app/transfer"
          className="inline-flex items-center justify-center rounded-md bg-ledger-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-ledger-800"
        >
          Transfer money
        </Link>
        <Link
          to="/app/beneficiaries"
          className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-ledger-700 hover:bg-slate-50"
        >
          Manage beneficiaries
        </Link>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Your accounts ({data.total_accounts})
          </h3>
          <Link to="/app/accounts" className="text-sm font-medium text-ledger-700 hover:underline">
            View all
          </Link>
        </div>
        <Card>
          {data.accounts.length === 0 ? (
            <EmptyState title="No accounts yet" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.accounts.map((account) => (
                <li key={account.id} className="flex items-center justify-between px-5 py-4">
                  <div>
                    <p className="font-mono text-sm text-ink">
                      {formatAccountNumber(account.account_number)}
                    </p>
                    <p className="text-xs text-slate-500">{account.account_type}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono tabular text-sm text-ink">
                      {formatMoney(account.balance, account.currency)}
                    </span>
                    <Badge status={account.status}>{account.status}</Badge>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}
