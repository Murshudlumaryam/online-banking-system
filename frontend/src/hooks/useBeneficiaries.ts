import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  beneficiariesService,
  type CreateBeneficiaryPayload,
  type UpdateBeneficiaryPayload,
} from "@/services/beneficiariesService";

export function useBeneficiaries() {
  return useQuery({
    queryKey: ["beneficiaries"],
    queryFn: beneficiariesService.list,
  });
}

export function useCreateBeneficiary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateBeneficiaryPayload) => beneficiariesService.create(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["beneficiaries"] }),
  });
}

export function useUpdateBeneficiary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateBeneficiaryPayload }) =>
      beneficiariesService.update(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["beneficiaries"] }),
  });
}

export function useDeleteBeneficiary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => beneficiariesService.remove(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["beneficiaries"] }),
  });
}
