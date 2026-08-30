import { useState } from "react";
import type { FormEvent } from "react";

import { useAdminAuditLogs } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";

interface AuditLogFilters {
  action?: string;
  user_id?: string;
  status?: string;
  request_id?: string;
}

export function AdminAuditLogsPage() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [userIdFilter, setUserIdFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [requestIdFilter, setRequestIdFilter] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<AuditLogFilters>({});

  const { data, isLoading, isError, error } = useAdminAuditLogs({ page, page_size: 20, ...appliedFilters });

  function handleFilterSubmit(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({
      action: actionFilter.trim() || undefined,
      user_id: userIdFilter.trim() || undefined,
      status: statusFilter || undefined,
      request_id: requestIdFilter.trim() || undefined,
    });
  }

  function handleClearFilters() {
    setActionFilter("");
    setUserIdFilter("");
    setStatusFilter("");
    setRequestIdFilter("");
    setAppliedFilters({});
    setPage(1);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-6">
        <form className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5" onSubmit={handleFilterSubmit}>
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
          <Select label="Status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Any</option>
            <option value="SUCCESS">Success</option>
            <option value="FAILED">Failed</option>
          </Select>
          <Input
            label="Request ID"
            placeholder="Correlates one request's events"
            value={requestIdFilter}
            onChange={(e) => setRequestIdFilter(e.target.value)}
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
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium text-ink">{entry.action}</span>
                      {entry.status && (
                        <Badge status={entry.status === "SUCCESS" ? "ACTIVE" : "BLOCKED"}>{entry.status}</Badge>
                      )}
                    </div>
                    <span className="text-xs text-slate-500">{formatDateTime(entry.created_at)}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-slate-500">
                    {entry.resource_type && <span>resource: {entry.resource_type}</span>}
                    {entry.user_id && <span className="font-mono">user: {entry.user_id}</span>}
                    {entry.ip_address && <span>ip: {entry.ip_address}</span>}
                    {entry.request_id && (
                      <span className="font-mono" title="Correlates every event from the same request">
                        request: {entry.request_id.slice(0, 8)}…
                      </span>
                    )}
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
