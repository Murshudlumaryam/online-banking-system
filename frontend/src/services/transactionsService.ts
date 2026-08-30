import { api } from "@/api/client";
import type {
  InitiateTransferResponse,
  PaginatedResponse,
  TransactionDetailResponse,
  TransactionResponse,
} from "@/types/api";

export interface TransferMoneyPayload {
  sender_account_id: string;
  receiver_account_number: string;
  amount: string;
  currency: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const transactionsService = {
  async initiateTransfer(payload: TransferMoneyPayload): Promise<InitiateTransferResponse> {
    return unwrap(api.POST("/api/v1/transactions/transfer", { body: payload }));
  },

  async resendOtp(transactionId: string): Promise<{ otp_expires_in_seconds: number; message: string }> {
    return unwrap(
      api.POST("/api/v1/transactions/{transaction_id}/resend-otp", {
        params: { path: { transaction_id: transactionId } },
      }),
    );
  },

  async confirmTransfer(transactionId: string, otpCode: string): Promise<TransactionResponse> {
    return unwrap(
      api.POST("/api/v1/transactions/{transaction_id}/confirm", {
        params: { path: { transaction_id: transactionId } },
        body: { otp_code: otpCode },
      }),
    );
  },

  async list(page: number, pageSize = 20): Promise<PaginatedResponse<TransactionResponse>> {
    return unwrap(
      api.GET("/api/v1/transactions", { params: { query: { page, page_size: pageSize } } }),
    );
  },

  async getById(transactionId: string): Promise<TransactionDetailResponse> {
    const result = await unwrap(
      api.GET("/api/v1/transactions/{transaction_id}", {
        params: { path: { transaction_id: transactionId } },
      }),
    );
    return { ...result, ledger_entries: result.ledger_entries ?? [] };
  },

  async searchByReference(reference: string): Promise<TransactionResponse> {
    return unwrap(api.GET("/api/v1/transactions/search", { params: { query: { reference } } }));
  },
};
