import { useState } from "react";
import { Link } from "react-router";

import { useAdminCustomers } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import type { CustomerStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";

export function AdminCustomersPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<CustomerStatus | "">("");
  const { data, isLoading, isError, error } = useAdminCustomers(page, status || undefined);

  return (
    <div className="flex flex-col gap-4">
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
                <li key={customer.id}>
                  <Link
                    to={`/admin/customers/${customer.id}`}
                    className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
                  >
                    <div>
                      <p className="text-sm font-medium text-ink">
                        {customer.first_name} {customer.last_name}
                      </p>
                      <p className="font-mono text-xs text-slate-500">{customer.customer_number}</p>
                    </div>
                    <Badge status={customer.status}>{customer.status}</Badge>
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
