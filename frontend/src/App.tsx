import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@/lib/router";

import { AuthProvider } from "@/context/AuthContext";
import { queryClient } from "@/lib/queryClient";
import { router } from "@/routes/router";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
