import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '@/lib/api/memory';

export function useMemorySegments(contextId: number) {
  return useQuery({
    queryKey: ['memory', contextId],
    queryFn: () => memoryApi.listSegments(contextId),
  });
}
