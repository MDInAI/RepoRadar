import { apiClient } from './client';

export interface MemorySegmentResponse {
  id: number;
  segment_key: string;
  content: string;
  content_type: string;
  created_at: string;
  updated_at: string;
}

export const memoryApi = {
  listSegments: async (contextId: number): Promise<MemorySegmentResponse[]> => {
    const response = await apiClient.get<MemorySegmentResponse[]>(`/obsession/contexts/${contextId}/memory`);
    return response.data;
  },

  getSegment: async (contextId: number, segmentKey: string): Promise<MemorySegmentResponse> => {
    const response = await apiClient.get<MemorySegmentResponse>(`/obsession/contexts/${contextId}/memory/${segmentKey}`);
    return response.data;
  },
};
