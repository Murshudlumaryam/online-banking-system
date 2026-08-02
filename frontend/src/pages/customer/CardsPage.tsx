import { useCards } from "@/hooks/useCards";
import { formatDate } from "@/lib/format";
import { getApiErrorMessage } from "@/lib/apiClient";
import { Badge } from "@/components/ui/Badge";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";

export function CardsPage() {
  const { data: cards, isLoading, isError, error } = useCards();

  if (isLoading) return <Spinner label="Loading cards" />;
  if (isError) return <ErrorBanner message={getApiErrorMessage(error)} />;

  if (!cards || cards.length === 0) {
    return (
      <Card className="p-6">
        <EmptyState title="No cards yet" description="Contact support to request a debit card." />
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => (
        <div
          key={card.id}
          className="flex aspect-[1.586/1] flex-col justify-between rounded-xl bg-gradient-to-br from-ledger-800 to-ledger-600 p-5 text-white shadow-card"
        >
          <div className="flex items-start justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-ledger-100">
              {card.card_type}
            </span>
            <Badge status={card.status}>{card.status}</Badge>
          </div>
          <div>
            <p className="font-mono text-lg tracking-widest">{card.masked_card_number}</p>
            <p className="mt-1 text-xs text-ledger-100">Expires {formatDate(card.expiry_date)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
