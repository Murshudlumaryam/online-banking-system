import { useQuery } from "@tanstack/react-query";

import { cardsService } from "@/services/cardsService";

export function useCards() {
  return useQuery({
    queryKey: ["cards"],
    queryFn: cardsService.list,
  });
}
