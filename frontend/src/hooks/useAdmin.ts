import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  adminService,
  type AuditLogFilters,
  type CreateAccountPayload,
  type CreateCardPayload,
  type CreateExchangeRatePayload,
  type DepositWithdrawalPayload,
} from "@/services/adminService";
import type { AccountStatus, CustomerStatus, TransactionStatus } from "@/types/api";

export function useAdminCustomers(page: number, status?: CustomerStatus) {
  return useQuery({
    queryKey: ["admin", "customers", page, status],
    queryFn: () => adminService.listCustomers(page, status),
  });
}

export function useAdminCustomer(customerId: string | undefined) {
  return useQuery({
    queryKey: ["admin", "customers", "detail", customerId],
    queryFn: () => adminService.getCustomer(customerId as string),
    enabled: Boolean(customerId),
  });
}

export function useUpdateCustomerStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ customerId, status }: { customerId: string; status: CustomerStatus }) =>
      adminService.updateCustomerStatus(customerId, status),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "customers"] }),
  });
}

export function useAdminAccounts(page: number, status?: AccountStatus) {
  return useQuery({
    queryKey: ["admin", "accounts", page, status],
    queryFn: () => adminService.listAccounts(page, status),
  });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAccountPayload) => adminService.createAccount(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] }),
  });
}

export function useUpdateAccountStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, status }: { accountId: string; status: AccountStatus }) =>
      adminService.updateAccountStatus(accountId, status),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] }),
  });
}

export function useDepositToAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, payload }: { accountId: string; payload: DepositWithdrawalPayload }) =>
      adminService.depositToAccount(accountId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] }),
  });
}

export function useWithdrawFromAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, payload }: { accountId: string; payload: DepositWithdrawalPayload }) =>
      adminService.withdrawFromAccount(accountId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] }),
  });
}

export function useCreateCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateCardPayload) => adminService.createCard(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] }),
  });
}

export function useBlockCard() {
  return useMutation({
    mutationFn: (cardId: string) => adminService.blockCard(cardId),
  });
}

export function useAdminTransactions(page: number, status?: TransactionStatus) {
  return useQuery({
    queryKey: ["admin", "transactions", page, status],
    queryFn: () => adminService.listTransactions(page, status),
  });
}

export function useAdminTransaction(transactionId: string | undefined) {
  return useQuery({
    queryKey: ["admin", "transactions", "detail", transactionId],
    queryFn: () => adminService.getTransaction(transactionId as string),
    enabled: Boolean(transactionId),
  });
}

export function useAdminAuditLogs(filters: AuditLogFilters) {
  return useQuery({
    queryKey: ["admin", "audit-logs", filters],
    queryFn: () => adminService.listAuditLogs(filters),
  });
}

export function useAdminExchangeRates() {
  return useQuery({
    queryKey: ["admin", "exchange-rates"],
    queryFn: adminService.listExchangeRates,
  });
}

export function useCreateExchangeRate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateExchangeRatePayload) => adminService.createExchangeRate(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "exchange-rates"] }),
  });
}
