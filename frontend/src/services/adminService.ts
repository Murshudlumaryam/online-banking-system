import { api } from "@/api/client";
import type {
  AccountResponse,
  AccountStatus,
  AuditLogResponse,
  BeneficiaryResponse,
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

export interface AdminCreateCustomerPayload {
  email: string;
  temporary_password: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone_number: string;
  address?: string;
  national_id: string;
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
  status?: string;
  request_id?: string;
  created_after?: string;
  created_before?: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const adminService = {
  async listCustomers(
    page: number,
    status?: CustomerStatus,
    search?: string,
  ): Promise<PaginatedResponse<CustomerProfile>> {
    return unwrap(
      api.GET("/api/v1/admin/customers", { params: { query: { page, status, search } } }),
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

  async listAccounts(
    page: number,
    status?: AccountStatus,
    search?: string,
  ): Promise<PaginatedResponse<AccountResponse>> {
    return unwrap(api.GET("/api/v1/admin/accounts", { params: { query: { page, status, search } } }));
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

  async deleteCard(cardId: string): Promise<void> {
    await unwrap(api.DELETE("/api/v1/admin/cards/{card_id}", { params: { path: { card_id: cardId } } }));
  },

  async listCards(page: number, status?: string): Promise<PaginatedResponse<CardResponse>> {
    return unwrap(
      api.GET("/api/v1/admin/cards", {
        params: { query: { page, status: status as never } },
      }),
    );
  },

  async listBeneficiaries(page: number): Promise<PaginatedResponse<BeneficiaryResponse>> {
    return unwrap(api.GET("/api/v1/admin/beneficiaries", { params: { query: { page } } }));
  },

  async createCustomer(payload: AdminCreateCustomerPayload): Promise<CustomerProfile> {
    return unwrap(api.POST("/api/v1/admin/customers", { body: payload }));
  },

  async listDeletedCustomers(page: number): Promise<PaginatedResponse<CustomerProfile>> {
    return unwrap(api.GET("/api/v1/admin/customers/deleted", { params: { query: { page } } }));
  },

  async deleteCustomer(customerId: string): Promise<void> {
    await unwrap(
      api.DELETE("/api/v1/admin/customers/{customer_id}", { params: { path: { customer_id: customerId } } }),
    );
  },

  async restoreCustomer(customerId: string): Promise<CustomerProfile> {
    return unwrap(
      api.POST("/api/v1/admin/customers/{customer_id}/restore", {
        params: { path: { customer_id: customerId } },
      }),
    );
  },

  async listDeletedBeneficiaries(page: number): Promise<PaginatedResponse<BeneficiaryResponse>> {
    return unwrap(api.GET("/api/v1/admin/beneficiaries/deleted", { params: { query: { page } } }));
  },

  async deleteBeneficiary(beneficiaryId: string): Promise<void> {
    await unwrap(
      api.DELETE("/api/v1/admin/beneficiaries/{beneficiary_id}", {
        params: { path: { beneficiary_id: beneficiaryId } },
      }),
    );
  },

  async restoreBeneficiary(beneficiaryId: string): Promise<BeneficiaryResponse> {
    return unwrap(
      api.POST("/api/v1/admin/beneficiaries/{beneficiary_id}/restore", {
        params: { path: { beneficiary_id: beneficiaryId } },
      }),
    );
  },

  async reverseTransaction(transactionId: string, reason: string): Promise<TransactionResponse> {
    return unwrap(
      api.POST("/api/v1/admin/transactions/{transaction_id}/reverse", {
        params: { path: { transaction_id: transactionId } },
        body: { reason },
      }),
    );
  },

  async listTransactions(
    page: number,
    status?: TransactionStatus,
    search?: string,
  ): Promise<PaginatedResponse<TransactionResponse>> {
    return unwrap(api.GET("/api/v1/admin/transactions", { params: { query: { page, status, search } } }));
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
