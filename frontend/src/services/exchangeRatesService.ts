import { api } from "@/api/client";
import type { ExchangeRateResponse } from "@/types/api";

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const exchangeRatesService = {
  async list(): Promise<ExchangeRateResponse[]> {
    return unwrap(api.GET("/api/v1/exchange-rates", {}));
  },
};
