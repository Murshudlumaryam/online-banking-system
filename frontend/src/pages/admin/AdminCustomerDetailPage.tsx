import { useState } from "react";
import type { FormEvent } from "react";
import { useParams } from "@/lib/router";

import { useAdminCustomer, useCreateAccount, useUpdateCustomerStatus } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import type { CustomerStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Card, ErrorBanner, Spinner } from "@/components/ui/Feedback";

export function AdminCustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const { data: customer, isLoading, isError, error } = useAdminCustomer(customerId);
  const updateStatus = useUpdateCustomerStatus();
  const createAccount = useCreateAccount();

  const [accountType, setAccountType] = useState<"CHECKING" | "SAVINGS">("CHECKING");
  const [currency, setCurrency] = useState("AZN");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdMessage, setCreatedMessage] = useState<string | null>(null);

  if (isLoading) return <Spinner label="Loading customer" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error, "Customer not found.")} />;
  if (!customer) return null;

  async function handleStatusChange(status: CustomerStatus) {
    if (!customerId) return;
    await updateStatus.mutateAsync({ customerId, status });
  }

  async function handleCreateAccount(event: FormEvent) {
    event.preventDefault();
    if (!customerId) return;
    setCreateError(null);
    setCreatedMessage(null);
    try {
      const account = await createAccount.mutateAsync({ customer_id: customerId, account_type: accountType, currency });
      setCreatedMessage(`Account ${account.account_number} opened.`);
    } catch (err) {
      setCreateError(getApiErrorMessage(err, "Couldn't open this account."));
    }
  }

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <Card className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-display text-lg text-ink">
              {customer.first_name} {customer.last_name}
            </h3>
            <p className="font-mono text-xs text-slate-500">{customer.customer_number}</p>
          </div>
          <Badge status={customer.status}>{customer.status}</Badge>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Phone</dt>
            <dd className="text-ink">{customer.phone_number}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Date of birth</dt>
            <dd className="text-ink">{formatDate(customer.date_of_birth)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-slate-500">Address</dt>
            <dd className="text-ink">{customer.address ?? "â€”"}</dd>
          </div>
        </dl>

        <div className="mt-6 flex gap-3 border-t border-slate-100 pt-6">
          {customer.status !== "BLOCKED" ? (
            <Button variant="danger" isLoading={updateStatus.isPending} onClick={() => handleStatusChange("BLOCKED")}>
              Block customer
            </Button>
          ) : (
            <Button isLoading={updateStatus.isPending} onClick={() => handleStatusChange("ACTIVE")}>
              Reactivate customer
            </Button>
          )}
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="font-display text-lg text-ink">Open a new account</h3>
        <form className="mt-4 flex flex-col gap-4" onSubmit={handleCreateAccount} noValidate>
          {createError && <ErrorBanner message={createError} />}
          {createdMessage && (
            <p className="rounded-md bg-forest-500/5 px-3 py-2 text-sm text-forest-600">{createdMessage}</p>
          )}
          <Select label="Account type" value={accountType} onChange={(e) => setAccountType(e.target.value as "CHECKING" | "SAVINGS")}>
            <option value="CHECKING">Checking</option>
            <option value="SAVINGS">Savings</option>
          </Select>
          <Input label="Currency" required maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
          <div>
            <Button type="submit" isLoading={createAccount.isPending}>
              Open account
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
