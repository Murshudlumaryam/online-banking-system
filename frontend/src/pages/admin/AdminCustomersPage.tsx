import { useState } from "react";
import { Link } from "react-router";

import {
  useAdminCustomers,
  useCreateCustomer,
  useDeletedCustomers,
  useDeleteCustomer,
  useRestoreCustomer,
} from "@/hooks/useAdmin";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { getApiErrorMessage } from "@/lib/apiClient";
import type { AdminCreateCustomerPayload } from "@/services/adminService";
import type { CustomerStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { CreateCustomerModal } from "@/components/modals/CreateCustomerModal";

function DeletedCustomersTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error } = useDeletedCustomers(page);
  const restoreCustomer = useRestoreCustomer();
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleRestore(customerId: string) {
    setFeedback(null);
    try {
      await restoreCustomer.mutateAsync(customerId);
      setFeedback("Customer restored.");
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't restore this customer."));
    }
  }

  if (isLoading) return <Spinner label="Loading deleted customers" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  return (
    <div className="flex flex-col gap-4">
      {feedback && <p className="text-sm text-slate-600">{feedback}</p>}
      <Card>
        {!data || data.items.length === 0 ? (
          <EmptyState title="No deleted customers" description="Everything removed shows up here, restorable." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.items.map((customer) => (
              <li key={customer.id} className="flex items-center justify-between px-5 py-4">
                <div>
                  <p className="text-sm font-medium text-ink">
                    {customer.first_name} {customer.last_name}
                  </p>
                  <p className="font-mono text-xs text-slate-500">{customer.customer_number}</p>
                </div>
                <Button
                  size="sm"
                  isLoading={restoreCustomer.isPending}
                  onClick={() => void handleRestore(customer.id)}
                >
                  Restore
                </Button>
              </li>
            ))}
          </ul>
        )}
        {data && (
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        )}
      </Card>
    </div>
  );
}

export function AdminCustomersPage() {
  const [tab, setTab] = useState<"active" | "deleted">("active");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<CustomerStatus | "">("");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput);
  const { data, isLoading, isError, error } = useAdminCustomers(page, status || undefined, search || undefined);
  const createCustomer = useCreateCustomer();
  const deleteCustomer = useDeleteCustomer();
  const [isCreating, setIsCreating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleCreateCustomer(payload: AdminCreateCustomerPayload) {
    setFeedback(null);
    try {
      await createCustomer.mutateAsync(payload);
      setIsCreating(false);
      setFeedback("Customer account created.");
    } catch {
      // Error surfaces inline in the modal via mutation.error — keep it open.
    }
  }

  async function handleDelete(customerId: string, name: string) {
    setFeedback(null);
    const confirmed = window.confirm(
      `Remove ${name}? Their accounts and transaction history are preserved and this can be undone from the Deleted tab.`,
    );
    if (!confirmed) return;
    try {
      await deleteCustomer.mutateAsync(customerId);
      setFeedback("Customer removed.");
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't remove this customer."));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 border-b border-slate-200">
        <button
          type="button"
          className={`px-3 py-2 text-sm font-medium ${
            tab === "active" ? "border-b-2 border-ledger-600 text-ink" : "text-slate-500"
          }`}
          onClick={() => setTab("active")}
        >
          Active
        </button>
        <button
          type="button"
          className={`px-3 py-2 text-sm font-medium ${
            tab === "deleted" ? "border-b-2 border-ledger-600 text-ink" : "text-slate-500"
          }`}
          onClick={() => setTab("deleted")}
        >
          Deleted
        </button>
      </div>

      {tab === "deleted" ? (
        <DeletedCustomersTab />
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap items-end gap-4">
              <div className="max-w-sm flex-1">
                <Input
                  label="Search"
                  placeholder="Name, email, phone, national ID, or customer number"
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
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value as CustomerStatus | "");
                    setPage(1);
                  }}
                >
                  <option value="">All statuses</option>
                  <option value="ACTIVE">Active</option>
                  <option value="BLOCKED">Blocked</option>
                  <option value="PENDING_VERIFICATION">Pending verification</option>
                </Select>
              </div>
            </div>
            <Button onClick={() => setIsCreating(true)}>Open account for customer</Button>
          </div>

          {feedback && <p className="text-sm text-slate-600">{feedback}</p>}

          {isCreating && (
            <CreateCustomerModal
              isSubmitting={createCustomer.isPending}
              errorMessage={
                createCustomer.isError
                  ? getApiErrorMessage(createCustomer.error, "Couldn't create this customer.")
                  : null
              }
              onSubmit={(payload) => void handleCreateCustomer(payload)}
              onCancel={() => setIsCreating(false)}
            />
          )}

          {isLoading ? (
            <Spinner label="Loading customers" />
          ) : isError ? (
            <ErrorBanner message={getApiErrorMessage(error)} />
          ) : (
            <Card>
              {!data || data.items.length === 0 ? (
                <EmptyState title="No customers found" />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {data.items.map((customer) => (
                    <li key={customer.id} className="flex items-center justify-between px-5 py-4 hover:bg-slate-50">
                      <Link to={`/admin/customers/${customer.id}`} className="flex-1">
                        <p className="text-sm font-medium text-ink">
                          {customer.first_name} {customer.last_name}
                        </p>
                        <p className="font-mono text-xs text-slate-500">{customer.customer_number}</p>
                      </Link>
                      <div className="flex items-center gap-3">
                        <Badge status={customer.status}>{customer.status}</Badge>
                        <Button
                          size="sm"
                          variant="ghost"
                          isLoading={deleteCustomer.isPending}
                          onClick={() =>
                            void handleDelete(customer.id, `${customer.first_name} ${customer.last_name}`)
                          }
                        >
                          Remove
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
        </>
      )}
    </div>
  );
}
