import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  scheduledPaymentsService,
  type CreateScheduledPaymentPayload,
} from "@/services/scheduledPaymentsService";

export function useScheduledPayments() {
  return useQuery({
    queryKey: ["scheduled-payments"],
    queryFn: scheduledPaymentsService.list,
  });
}

export function useCreateScheduledPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateScheduledPaymentPayload) => scheduledPaymentsService.create(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["scheduled-payments"] }),
  });
}

export function useCancelScheduledPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) => scheduledPaymentsService.cancel(scheduleId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["scheduled-payments"] }),
  });
}
