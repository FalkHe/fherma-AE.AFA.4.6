import { QueryClient } from "@tanstack/react-query";

/**
 * The application's single query cache.
 *
 * It lives in its own module rather than in `main.tsx` because the API client
 * middleware has to reach it: an unexpected 401 has to invalidate the cached
 * identity, and middleware runs outside React, where `useQueryClient()` is not
 * available. Components keep using `useQueryClient()` — this instance is the one
 * `main.tsx` hands to the provider.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Server state is refetched on SSE notifications (see architecture.md),
      // not on every window focus.
      refetchOnWindowFocus: false,
    },
  },
});
