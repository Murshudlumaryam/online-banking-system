import { useState } from "react";
import type { FormEvent } from "react";

import { useAdminAuditLogs } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";

export function AdminAuditLogsPage() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [userIdFilter, setUserIdFilter] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<{ action?: string; user_id?: string }>({});

  const { data, isLoading, isError, error } = useAdminAuditLogs({ page, page_size: 20, ...appliedFilters });

  function handleFilterSubmit(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({
      action: actionFilter.trim() || undefined,
      user_id: userIdFilter.trim() || undefined,
    });
  }

  function handleClearFilters() {
    setActionFilter("");
    setUserIdFilter("");
    setAppliedFilters({});
    setPage(1);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-6">
        <form className="grid grid-cols-1 gap-4 sm:grid-cols-3" onSubmit={handleFilterSubmit}>
          <Input
            label="Action"
            placeholder="e.g. TRANSFER_COMPLETED"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
          />
          <Input
            label="User ID"
            placeholder="UUID"
            value={userIdFilter}
            onChange={(e) => setUserIdFilter(e.target.value)}
          />
          <div className="flex items-end gap-2">
            <Button type="submit">Apply filters</Button>
            <Button type="button" variant="ghost" onClick={handleClearFilters}>
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {isLoading ? (
        <Spinner label="Loading audit logs" />
      ) : isError ? (
        <ErrorBanner message={getApiErrorMessage(error)} />
      ) : (
        <Card>
          {!data || data.items.length === 0 ? (
            <EmptyState title="No matching audit entries" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.items.map((entry) => (
                <li key={entry.id} className="px-5 py-4">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm font-medium text-ink">{entry.action}</span>
                    <span className="text-xs text-slate-500">{formatDateTime(entry.created_at)}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-slate-500">
                    {entry.resource_type && <span>resource: {entry.resource_type}</span>}
                    {entry.user_id && <span className="font-mono">user: {entry.user_id}</span>}
                    {entry.ip_address && <span>ip: {entry.ip_address}</span>}
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
