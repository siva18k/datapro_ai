import { useMutation } from "@tanstack/react-query";
import { devBootstrap, type DevBootstrapResponse } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";

export function useStartApiFromWeb() {
  const { waitUntilOnline } = useApiConnection();

  return useMutation({
    mutationFn: async (): Promise<DevBootstrapResponse> => {
      const res = await devBootstrap.startApi();
      if (!res.ok && !res.managed && !res.reachable) {
        return res;
      }
      const online = await waitUntilOnline({ maxWaitMs: 20_000, intervalMs: 500 });
      return { ...res, reachable: online, ok: online };
    },
  });
}
