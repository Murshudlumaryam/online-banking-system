import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { cardsService } from "@/services/cardsService";

export function useCards() {
  return useQuery({
    queryKey: ["cards"],
    queryFn: cardsService.list,
  });
}

export function useBlockCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cardId: string) => cardsService.block(cardId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["cards"] }),
  });
}
