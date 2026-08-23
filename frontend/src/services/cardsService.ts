import { api } from "@/api/client";
import type { CardResponse, TransactionResponse } from "@/types/api";

export interface CardPaymentPayload {
  amount: string;
  currency: string;
  merchant_name: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const cardsService = {
  async list(): Promise<CardResponse[]> {
    return unwrap(api.GET("/api/v1/cards", {}));
  },

  async getById(cardId: string): Promise<CardResponse> {
    return unwrap(api.GET("/api/v1/cards/{card_id}", { params: { path: { card_id: cardId } } }));
  },

  async block(cardId: string): Promise<CardResponse> {
    return unwrap(api.POST("/api/v1/cards/{card_id}/block", { params: { path: { card_id: cardId } } }));
  },

  async pay(cardId: string, payload: CardPaymentPayload): Promise<TransactionResponse> {
    return unwrap(
      api.POST("/api/v1/cards/{card_id}/pay", {
        params: { path: { card_id: cardId } },
        body: payload,
      }),
    );
  },
};
