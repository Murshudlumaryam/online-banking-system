import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { transactionsService, type TransferMoneyPayload } from "@/services/transactionsService";

export function useTransactions(page: number) {
  return useQuery({
    queryKey: ["transactions", page],
    queryFn: () => transactionsService.list(page),
  });
}

export function useTransaction(transactionId: string | undefined) {
  return useQuery({
    queryKey: ["transactions", "detail", transactionId],
    queryFn: () => transactionsService.getById(transactionId as string),
    enabled: Boolean(transactionId),
  });
}

export function useInitiateTransfer() {
  return useMutation({
    mutationFn: (payload: TransferMoneyPayload) => transactionsService.initiateTransfer(payload),
  });
}

export function useResendOtp() {
  return useMutation({
    mutationFn: (transactionId: string) => transactionsService.resendOtp(transactionId),
  });
}

export function useConfirmTransfer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ transactionId, otpCode }: { transactionId: string; otpCode: string }) =>
      transactionsService.confirmTransfer(transactionId, otpCode),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
