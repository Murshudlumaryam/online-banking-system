import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { customersService, type UpdateProfilePayload } from "@/services/customersService";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: customersService.getDashboard,
  });
}

export function useMyProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: customersService.getMyProfile,
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdateProfilePayload) => customersService.updateMyProfile(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
