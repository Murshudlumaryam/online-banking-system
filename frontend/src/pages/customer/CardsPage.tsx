import { useState } from "react";

import { useBlockCard, useCards } from "@/hooks/useCards";
import { formatDate } from "@/lib/format";
import { getApiErrorMessage } from "@/lib/apiClient";
import type { CardResponse } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";

function CardTile({ card }: { card: CardResponse }) {
  const blockCard = useBlockCard();
  const [error, setError] = useState<string | null>(null);

  async function handleBlock() {
    setError(null);
    const confirmed = window.confirm(
      "Block this card? This can't be undone from here — you'll need to ask an admin to issue a replacement.",
    );
    if (!confirmed) return;
    try {
      await blockCard.mutateAsync(card.id);
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't block this card."));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex aspect-[1.586/1] flex-col justify-between rounded-xl bg-gradient-to-br from-ledger-800 to-ledger-600 p-5 text-white shadow-card">
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
      {error && <ErrorBanner message={error} />}
      {card.status === "ACTIVE" && (
        <Button
          size="sm"
          variant="danger"
          isLoading={blockCard.isPending}
          onClick={() => void handleBlock()}
        >
          Report lost or stolen
        </Button>
      )}
    </div>
  );
}

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
        <CardTile key={card.id} card={card} />
      ))}
    </div>
  );
}
