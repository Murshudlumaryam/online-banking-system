import { useState } from "react";

import { useAdminCards, useBlockCard, useDeleteCard } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import type { CardStatus } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";

const STATUS_OPTIONS: CardStatus[] = ["ACTIVE", "BLOCKED", "EXPIRED"];
const PAGE_SIZE = 20;

export function AdminCardsPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<CardStatus | "">("");
  const { data, isLoading, isError, error } = useAdminCards(page, statusFilter || undefined);
  const blockCard = useBlockCard();
  const deleteCard = useDeleteCard();
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleBlock(cardId: string) {
    setFeedback(null);
    try {
      await blockCard.mutateAsync(cardId);
      setFeedback("Card blocked.");
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't block this card."));
    }
  }

  async function handleDelete(cardId: string) {
    setFeedback(null);
    const confirmed = window.confirm(
      "Remove this card? It will disappear from the customer's card list. Its transaction history is kept for audit purposes.",
    );
    if (!confirmed) return;
    try {
      await deleteCard.mutateAsync(cardId);
      setFeedback("Card removed.");
    } catch (err) {
      setFeedback(getApiErrorMessage(err, "Couldn't remove this card."));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-xs">
        <Select
          label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as CardStatus | "");
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </div>

      {feedback && <p className="text-sm text-slate-600">{feedback}</p>}

      {isLoading ? (
        <Spinner label="Loading cards" />
      ) : isError ? (
        <ErrorBanner message={getApiErrorMessage(error)} />
      ) : (
        <Card>
          {!data || data.items.length === 0 ? (
            <EmptyState title="No cards found" />
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Cardholder</th>
                  <th className="px-4 py-3">Card number</th>
                  <th className="px-4 py-3">Account</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Expires</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((card) => (
                  <tr key={card.id}>
                    <td className="px-4 py-3 text-ink">{card.customer_name ?? <span className="text-slate-400">—</span>}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink">{card.masked_card_number}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {card.account_number ?? <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{card.card_type}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(card.expiry_date)}</td>
                    <td className="px-4 py-3">
                      <Badge status={card.status}>{card.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {card.status === "ACTIVE" && (
                          <Button
                            size="sm"
                            variant="danger"
                            isLoading={blockCard.isPending}
                            onClick={() => void handleBlock(card.id)}
                          >
                            Block
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          isLoading={deleteCard.isPending}
                          onClick={() => void handleDelete(card.id)}
                        >
                          Remove
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data && (
            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />
          )}
        </Card>
      )}
    </div>
  );
}
