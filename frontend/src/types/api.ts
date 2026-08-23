// Mirrors the backend Pydantic schemas (see backend/app/modules/*/schemas.py).
// Keeping these in sync manually is a deliberate Phase 5 tradeoff — an
// OpenAPI-generated client is a good Phase 6 hardening candidate.

export type UserRole = "ADMIN" | "CUSTOMER";
export type CustomerStatus = "ACTIVE" | "BLOCKED" | "PENDING_VERIFICATION";
export type AccountStatus = "ACTIVE" | "BLOCKED" | "CLOSED" | "PENDING";
export type CardStatus = "ACTIVE" | "BLOCKED" | "EXPIRED";
export type TransactionStatus = "PENDING" | "SUCCESS" | "FAILED" | "REVERSED";
export type LedgerEntryType = "DEBIT" | "CREDIT";

export interface ApiErrorBody {
  error_code: string;
  message: string;
  details: string[];
  request_id: string;
}

export interface TokenResponse {
  // The refresh token is never in the response body — it travels only as
  // an HttpOnly, Secure, SameSite=Strict cookie the browser manages
  // automatically (see backend/app/modules/auth/cookies.py). JavaScript
  // never sees it, so it can't be exfiltrated by an XSS payload the way a
  // localStorage-held token could be.
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginResponse {
  mfa_required: boolean;
  challenge_token: string | null;
  access_token: string | null;
  token_type: string;
  expires_in: number | null;
}

export interface CustomerSummary {
  id: string;
  customer_number: string;
  first_name: string;
  last_name: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  customer: CustomerSummary;
}

export interface CustomerProfile {
  id: string;
  customer_number: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone_number: string;
  address: string | null;
  national_id: string | null;
  status: CustomerStatus;
  totp_enabled: boolean;
}

export interface CurrencyBalance {
  currency: string;
  total_balance: string;
}

export interface DashboardResponse {
  customer_number: string;
  full_name: string;
  total_accounts: number;
  balances_by_currency: CurrencyBalance[];
  accounts: AccountResponse[];
}

export interface AccountResponse {
  id: string;
  account_number: string;
  account_type: string;
  currency: string;
  balance: string;
  status: AccountStatus;
}

export interface AccountBalanceResponse {
  account_id: string;
  currency: string;
  balance: string;
}

export interface CardResponse {
  id: string;
  account_id: string;
  masked_card_number: string;
  card_type: string;
  expiry_date: string;
  status: CardStatus;
}

export interface BeneficiaryResponse {
  id: string;
  beneficiary_account_number: string;
  beneficiary_name: string;
  nickname: string | null;
}

export interface ExchangeRateResponse {
  id: string;
  source_currency: string;
  target_currency: string;
  rate: string;
  valid_from: string;
  valid_to: string | null;
}

export interface LedgerEntryResponse {
  id: string;
  account_id: string;
  entry_type: LedgerEntryType;
  amount: string;
  currency: string;
  balance_before: string;
  balance_after: string;
  created_at: string;
}

export type TransactionType = "TRANSFER" | "DEPOSIT" | "WITHDRAWAL" | "CARD_PAYMENT";

export interface TransactionResponse {
  id: string;
  reference_number: string;
  transaction_type: TransactionType;
  // Nullable: a DEPOSIT has no sender (money entered from outside this
  // closed-loop system) and a WITHDRAWAL has no receiver (money left it).
  sender_account_id: string | null;
  receiver_account_id: string | null;
  amount: string;
  currency: string;
  converted_amount: string | null;
  status: TransactionStatus;
  failure_reason: string | null;
  note: string | null;
  // Set only for CARD_PAYMENT — which card was charged.
  card_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface TransactionDetailResponse extends TransactionResponse {
  ledger_entries: LedgerEntryResponse[];
}

export interface InitiateTransferResponse {
  transaction: TransactionResponse;
  otp_expires_in_seconds: number;
  message: string;
}

export interface AuditLogResponse {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  log_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
