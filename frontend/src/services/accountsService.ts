import { api } from "@/api/client";
import type { AccountBalanceResponse, AccountResponse } from "@/types/api";

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const accountsService = {
  async list(): Promise<AccountResponse[]> {
    return unwrap(api.GET("/api/v1/accounts", {}));
  },

  async getById(accountId: string): Promise<AccountResponse> {
    return unwrap(api.GET("/api/v1/accounts/{account_id}", { params: { path: { account_id: accountId } } }));
  },

  async getBalance(accountId: string): Promise<AccountBalanceResponse> {
    return unwrap(
      api.GET("/api/v1/accounts/{account_id}/balance", { params: { path: { account_id: accountId } } }),
    );
  },

  /** Returns a Blob (PDF) — statements aren't JSON, so this bypasses the typed unwrap helper. */
  async downloadStatement(accountId: string, startDate?: string, endDate?: string): Promise<Blob> {
    const { response } = await api.GET("/api/v1/accounts/{account_id}/statement", {
      params: {
        path: { account_id: accountId },
        query: { start_date: startDate, end_date: endDate },
      },
      parseAs: "blob",
    });
    if (!response.ok) throw new Error("Failed to download statement");
    return response.blob();
  },
};
