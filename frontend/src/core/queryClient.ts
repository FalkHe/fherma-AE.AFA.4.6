import { QueryClient } from "@tanstack/react-query";

// A factory, not a module-scoped singleton: `main.tsx` creates one instance
// at module scope, and every test creates its own (step-0.1.md §6.2, §6.6).
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  });
}
