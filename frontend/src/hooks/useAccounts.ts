import { useQuery } from "@tanstack/react-query";

import { accountsService } from "@/services/accountsService";

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: accountsService.list,
  });
}

export function useAccount(accountId: string | undefined) {
  return useQuery({
    queryKey: ["accounts", accountId],
    queryFn: () => accountsService.getById(accountId as string),
    enabled: Boolean(accountId),
  });
}
