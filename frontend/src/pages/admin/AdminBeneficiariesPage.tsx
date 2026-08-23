import { useState } from "react";

import { useAdminBeneficiaries } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";

const PAGE_SIZE = 20;

export function AdminBeneficiariesPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error } = useAdminBeneficiaries(page);

  if (isLoading) return <Spinner label="Loading beneficiaries" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  return (
    <Card>
      {!data || data.items.length === 0 ? (
        <EmptyState title="No beneficiaries found" />
      ) : (
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Nickname</th>
              <th className="px-4 py-3">Beneficiary name</th>
              <th className="px-4 py-3">Account number</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.items.map((b) => (
              <tr key={b.id}>
                <td className="px-4 py-3 text-ink">{b.nickname ?? <span className="text-slate-400">—</span>}</td>
                <td className="px-4 py-3 text-slate-600">{b.beneficiary_name}</td>
                <td className="px-4 py-3 font-mono text-xs text-ink">{b.beneficiary_account_number}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />}
    </Card>
  );
}
