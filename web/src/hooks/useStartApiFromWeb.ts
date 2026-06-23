import { useMutation } from "@tanstack/react-query";
import { useApiConnection } from "../context/ApiConnectionContext";

export function useStartApiFromWeb() {
  const { startApiServer } = useApiConnection();

  return useMutation({
    mutationFn: startApiServer,
  });
}
