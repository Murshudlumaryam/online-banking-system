import { useState } from "react";
import type { FormEvent } from "react";

import { useBlockCard, useCards, usePayWithCard } from "@/hooks/useCards";
import { formatDate, formatMoney } from "@/lib/format";
import { getApiErrorMessage } from "@/lib/apiClient";
import type { CardResponse } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";

function PayWithCardForm({ cardId, onDone }: { cardId: string; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("AZN");
  const [merchantName, setMerchantName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const payWithCard = usePayWithCard();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const transaction = await payWithCard.mutateAsync({
        cardId,
        payload: { amount, currency, merchant_name: merchantName.trim() },
      });
      setSuccessMessage(`Paid ${formatMoney(transaction.amount, transaction.currency)} to ${merchantName}.`);
      setAmount("");
      setMerchantName("");
    } catch (err) {
      setError(getApiErrorMessage(err, "Couldn't complete this payment."));
    }
  }

  return (
    <form className="mt-2 flex flex-col gap-3 rounded-md border border-slate-200 p-4" onSubmit={handleSubmit} noValidate>
      {error && <ErrorBanner message={error} />}
      {successMessage && (
        <p className="rounded-md bg-forest-500/5 px-3 py-2 text-sm text-forest-600">{successMessage}</p>
      )}
      <p className="text-xs text-slate-500">
        Simulates a card purchase — no real merchant network is involved, this just charges the account
        behind this card.
      </p>
      <Input
        label="Merchant"
        required
        placeholder="e.g. Corner Grocery"
        value={merchantName}
        onChange={(e) => setMerchantName(e.target.value)}
      />
      <div className="grid grid-cols-2 gap-3">
        <Input
          label={`Amount (${currency})`}
          required
          type="number"
          step="0.01"
          min="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Input
          label="Currency"
          required
          maxLength={3}
          value={currency}
          onChange={(e) => setCurrency(e.target.value.toUpperCase())}
        />
      </div>
      <div className="flex gap-3">
        <Button type="submit" size="sm" isLoading={payWithCard.isPending}>
          Pay
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Close
        </Button>
      </div>
    </form>
  );
}

function CardTile({ card }: { card: CardResponse }) {
  const blockCard = useBlockCard();
  const [error, setError] = useState<string | null>(null);
  const [isPaying, setIsPaying] = useState(false);

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
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setIsPaying((v) => !v)}>
            {isPaying ? "Cancel payment" : "Pay with this card"}
          </Button>
          <Button
            size="sm"
            variant="danger"
            isLoading={blockCard.isPending}
            onClick={() => void handleBlock()}
          >
            Report lost or stolen
          </Button>
        </div>
      )}
      {isPaying && <PayWithCardForm cardId={card.id} onDone={() => setIsPaying(false)} />}
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
