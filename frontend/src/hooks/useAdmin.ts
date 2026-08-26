import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  adminService,
  type AdminCreateCustomerPayload,
  type AuditLogFilters,
  type CreateAccountPayload,
  type CreateCardPayload,
  type CreateExchangeRatePayload,
  type DepositWithdrawalPayload,
} from "@/services/adminService";
import type { AccountStatus, CustomerStatus, TransactionStatus } from "@/types/api";

export function useAdminCustomers(page: number, status?: CustomerStatus, search?: string) {
  return useQuery({
    queryKey: ["admin", "customers", page, status, search],
    queryFn: () => adminService.listCustomers(page, status, search),
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

export function useAdminAccounts(page: number, status?: AccountStatus, search?: string) {
  return useQuery({
    queryKey: ["admin", "accounts", page, status, search],
    queryFn: () => adminService.listAccounts(page, status, search),
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

export function useDeleteCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cardId: string) => adminService.deleteCard(cardId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "cards"] }),
  });
}

export function useAdminTransactions(page: number, status?: TransactionStatus, search?: string) {
  return useQuery({
    queryKey: ["admin", "transactions", page, status, search],
    queryFn: () => adminService.listTransactions(page, status, search),
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

export function useAdminCards(page: number, status?: string) {
  return useQuery({
    queryKey: ["admin", "cards", page, status],
    queryFn: () => adminService.listCards(page, status),
  });
}

export function useAdminBeneficiaries(page: number) {
  return useQuery({
    queryKey: ["admin", "beneficiaries", page],
    queryFn: () => adminService.listBeneficiaries(page),
  });
}

export function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AdminCreateCustomerPayload) => adminService.createCustomer(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "customers"] }),
  });
}

export function useReverseTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ transactionId, reason }: { transactionId: string; reason: string }) =>
      adminService.reverseTransaction(transactionId, reason),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "transactions"] }),
  });
}

export function useDeletedCustomers(page: number) {
  return useQuery({
    queryKey: ["admin", "customers", "deleted", page],
    queryFn: () => adminService.listDeletedCustomers(page),
  });
}

export function useDeleteCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) => adminService.deleteCustomer(customerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    },
  });
}

export function useRestoreCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) => adminService.restoreCustomer(customerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    },
  });
}

export function useDeletedBeneficiaries(page: number) {
  return useQuery({
    queryKey: ["admin", "beneficiaries", "deleted", page],
    queryFn: () => adminService.listDeletedBeneficiaries(page),
  });
}

export function useDeleteBeneficiary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (beneficiaryId: string) => adminService.deleteBeneficiary(beneficiaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "beneficiaries"] });
    },
  });
}

export function useRestoreBeneficiary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (beneficiaryId: string) => adminService.restoreBeneficiary(beneficiaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "beneficiaries"] });
    },
  });
}
