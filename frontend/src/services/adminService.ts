import { api } from "@/api/client";
import type {
  AccountResponse,
  AccountStatus,
  AuditLogResponse,
  CardResponse,
  CustomerProfile,
  CustomerStatus,
  ExchangeRateResponse,
  PaginatedResponse,
  TransactionDetailResponse,
  TransactionResponse,
  TransactionStatus,
} from "@/types/api";

export interface CreateAccountPayload {
  customer_id: string;
  account_type: "CHECKING" | "SAVINGS";
  currency: string;
}

export interface DepositWithdrawalPayload {
  amount: string;
  currency: string;
  note?: string;
}

export interface CreateCardPayload {
  account_id: string;
  card_type: "DEBIT" | "CREDIT";
  validity_years?: number;
}

export interface CreateExchangeRatePayload {
  source_currency: string;
  target_currency: string;
  rate: string;
}

export interface AuditLogFilters {
  page?: number;
  page_size?: number;
  user_id?: string;
  action?: string;
  resource_type?: string;
  created_after?: string;
  created_before?: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const adminService = {
  async listCustomers(page: number, status?: CustomerStatus): Promise<PaginatedResponse<CustomerProfile>> {
    return unwrap(
      api.GET("/api/v1/admin/customers", { params: { query: { page, status } } }),
    );
  },

  async getCustomer(customerId: string): Promise<CustomerProfile> {
    return unwrap(
      api.GET("/api/v1/admin/customers/{customer_id}", { params: { path: { customer_id: customerId } } }),
    );
  },

  async updateCustomerStatus(customerId: string, status: CustomerStatus): Promise<CustomerProfile> {
    return unwrap(
      api.PATCH("/api/v1/admin/customers/{customer_id}/status", {
        params: { path: { customer_id: customerId } },
        body: { status },
      }),
    );
  },

  async listAccounts(page: number, status?: AccountStatus): Promise<PaginatedResponse<AccountResponse>> {
    return unwrap(api.GET("/api/v1/admin/accounts", { params: { query: { page, status } } }));
  },

  async createAccount(payload: CreateAccountPayload): Promise<AccountResponse> {
    return unwrap(api.POST("/api/v1/admin/accounts", { body: payload }));
  },

  async updateAccountStatus(accountId: string, status: AccountStatus): Promise<AccountResponse> {
    return unwrap(
      api.PATCH("/api/v1/admin/accounts/{account_id}/status", {
        params: { path: { account_id: accountId } },
        body: { status },
      }),
    );
  },

  async depositToAccount(accountId: string, payload: DepositWithdrawalPayload): Promise<TransactionResponse> {
    return unwrap(
      api.POST("/api/v1/admin/accounts/{account_id}/deposit", {
        params: { path: { account_id: accountId } },
        body: payload,
      }),
    );
  },

  async withdrawFromAccount(accountId: string, payload: DepositWithdrawalPayload): Promise<TransactionResponse> {
    return unwrap(
      api.POST("/api/v1/admin/accounts/{account_id}/withdraw", {
        params: { path: { account_id: accountId } },
        body: payload,
      }),
    );
  },

  async createCard(payload: CreateCardPayload): Promise<CardResponse> {
    return unwrap(
      api.POST("/api/v1/admin/cards", {
        body: { ...payload, validity_years: payload.validity_years ?? 4 },
      }),
    );
  },

  async blockCard(cardId: string): Promise<CardResponse> {
    return unwrap(
      api.PATCH("/api/v1/admin/cards/{card_id}/block", { params: { path: { card_id: cardId } } }),
    );
  },

  async listTransactions(
    page: number,
    status?: TransactionStatus,
  ): Promise<PaginatedResponse<TransactionResponse>> {
    return unwrap(api.GET("/api/v1/admin/transactions", { params: { query: { page, status } } }));
  },

  async getTransaction(transactionId: string): Promise<TransactionDetailResponse> {
    const result = await unwrap(
      api.GET("/api/v1/admin/transactions/{transaction_id}", {
        params: { path: { transaction_id: transactionId } },
      }),
    );
    return { ...result, ledger_entries: result.ledger_entries ?? [] };
  },

  async listAuditLogs(filters: AuditLogFilters): Promise<PaginatedResponse<AuditLogResponse>> {
    return unwrap(api.GET("/api/v1/admin/audit-logs", { params: { query: filters } }));
  },

  async listExchangeRates(): Promise<ExchangeRateResponse[]> {
    return unwrap(api.GET("/api/v1/admin/exchange-rates", {}));
  },

  async createExchangeRate(payload: CreateExchangeRatePayload): Promise<ExchangeRateResponse> {
    return unwrap(api.POST("/api/v1/admin/exchange-rates", { body: payload }));
  },
};
