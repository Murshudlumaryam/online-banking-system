import { useQuery } from "@tanstack/react-query";

import { exchangeRatesService } from "@/services/exchangeRatesService";

export function useExchangeRates() {
  return useQuery({
    queryKey: ["exchange-rates"],
    queryFn: exchangeRatesService.list,
    staleTime: 60_000,
  });
}
