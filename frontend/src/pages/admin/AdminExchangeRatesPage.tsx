import { useState } from "react";
import type { FormEvent } from "react";

import { useAdminExchangeRates, useCreateExchangeRate } from "@/hooks/useAdmin";
import { getApiErrorMessage } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";

export function AdminExchangeRatesPage() {
  const { data: rates, isLoading, isError, error } = useAdminExchangeRates();
  const createRate = useCreateExchangeRate();

  const [sourceCurrency, setSourceCurrency] = useState("");
  const [targetCurrency, setTargetCurrency] = useState("");
  const [rate, setRate] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    try {
      await createRate.mutateAsync({
        source_currency: sourceCurrency.toUpperCase(),
        target_currency: targetCurrency.toUpperCase(),
        rate,
      });
      setSourceCurrency("");
      setTargetCurrency("");
      setRate("");
    } catch (err) {
      setFormError(getApiErrorMessage(err, "Couldn't add this rate."));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="p-6">
        <h3 className="font-display text-lg text-ink">Add an exchange rate</h3>
        <form className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4" onSubmit={handleSubmit} noValidate>
          {formError && <div className="col-span-full"><ErrorBanner message={formError} /></div>}
          <Input label="From" required maxLength={3} value={sourceCurrency} onChange={(e) => setSourceCurrency(e.target.value)} />
          <Input label="To" required maxLength={3} value={targetCurrency} onChange={(e) => setTargetCurrency(e.target.value)} />
          <Input label="Rate" required inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />
          <div className="flex items-end">
            <Button type="submit" isLoading={createRate.isPending} className="w-full">
              Add rate
            </Button>
          </div>
        </form>
      </Card>

      {isLoading ? (
        <Spinner label="Loading exchange rates" />
      ) : isError ? (
        <ErrorBanner message={getApiErrorMessage(error)} />
      ) : (
        <Card>
          {!rates || rates.length === 0 ? (
            <EmptyState title="No exchange rates configured" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {rates.map((r) => (
                <li key={r.id} className="flex items-center justify-between px-5 py-4">
                  <span className="font-mono text-sm text-ink">
                    {r.source_currency} &rarr; {r.target_currency}
                  </span>
                  <div className="text-right">
                    <p className="font-mono tabular text-sm text-ink">{r.rate}</p>
                    <p className="text-xs text-slate-500">since {formatDateTime(r.valid_from)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}
