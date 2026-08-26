import { useState } from "react";

import {
  useAdminBeneficiaries,
  useDeleteBeneficiary,
  useDeletedBeneficiaries,
  useRestoreBeneficiary,
} from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";

const PAGE_SIZE = 20;

function DeletedBeneficiariesTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error } = useDeletedBeneficiaries(page);
  const restoreBeneficiary = useRestoreBeneficiary();
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleRestore(beneficiaryId: string) {
    setFeedback(null);
    try {
      await restoreBeneficiary.mutateAsync(beneficiaryId);
      setFeedback("Beneficiary restored.");
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't restore this beneficiary."));
    }
  }

  if (isLoading) return <Spinner label="Loading deleted beneficiaries" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  return (
    <div className="flex flex-col gap-4">
      {feedback && <p className="text-sm text-slate-600">{feedback}</p>}
      <Card>
        {!data || data.items.length === 0 ? (
          <EmptyState title="No deleted beneficiaries" />
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Nickname</th>
                <th className="px-4 py-3">Beneficiary name</th>
                <th className="px-4 py-3">Account number</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((b) => (
                <tr key={b.id}>
                  <td className="px-4 py-3 text-ink">{b.nickname ?? <span className="text-slate-400">—</span>}</td>
                  <td className="px-4 py-3 text-slate-600">{b.beneficiary_name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink">{b.beneficiary_account_number}</td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      size="sm"
                      isLoading={restoreBeneficiary.isPending}
                      onClick={() => void handleRestore(b.id)}
                    >
                      Restore
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />}
      </Card>
    </div>
  );
}

export function AdminBeneficiariesPage() {
  const [tab, setTab] = useState<"active" | "deleted">("active");
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error } = useAdminBeneficiaries(page);
  const deleteBeneficiary = useDeleteBeneficiary();
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleDelete(beneficiaryId: string, name: string) {
    setFeedback(null);
    const confirmed = window.confirm(`Remove beneficiary "${name}"? This can be undone from the Deleted tab.`);
    if (!confirmed) return;
    try {
      await deleteBeneficiary.mutateAsync(beneficiaryId);
      setFeedback("Beneficiary removed.");
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't remove this beneficiary."));
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
        <DeletedBeneficiariesTab />
      ) : (
        <>
          {feedback && <p className="text-sm text-slate-600">{feedback}</p>}
          {isLoading ? (
            <Spinner label="Loading beneficiaries" />
          ) : isError ? (
            <ErrorBanner message={getApiErrorMessage(error)} />
          ) : (
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
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.items.map((b) => (
                      <tr key={b.id}>
                        <td className="px-4 py-3 text-ink">
                          {b.nickname ?? <span className="text-slate-400">—</span>}
                        </td>
                        <td className="px-4 py-3 text-slate-600">{b.beneficiary_name}</td>
                        <td className="px-4 py-3 font-mono text-xs text-ink">{b.beneficiary_account_number}</td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            size="sm"
                            variant="ghost"
                            isLoading={deleteBeneficiary.isPending}
                            onClick={() => void handleDelete(b.id, b.beneficiary_name)}
                          >
                            Remove
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
