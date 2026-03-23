import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addRepositoryToFamily,
  createIdeaFamily,
  deleteIdeaFamily,
  fetchIdeaFamilies,
  fetchIdeaFamily,
  removeRepositoryFromFamily,
  updateIdeaFamily,
  type CreateIdeaFamilyRequest,
  type IdeaFamily,
  type IdeaFamilyDetail,
  type UpdateIdeaFamilyRequest,
} from "@/api/idea-families";

export function useIdeaFamilies() {
  return useQuery({
    queryKey: ["idea-families"],
    queryFn: fetchIdeaFamilies,
  });
}

export function useIdeaFamily(familyId: number | null) {
  return useQuery({
    queryKey: ["idea-families", familyId],
    queryFn: () => fetchIdeaFamily(familyId!),
    enabled: familyId !== null,
  });
}

export function useCreateIdeaFamily() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateIdeaFamilyRequest) => createIdeaFamily(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idea-families"] });
    },
  });
}

export function useUpdateIdeaFamily() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ familyId, data }: { familyId: number; data: UpdateIdeaFamilyRequest }) =>
      updateIdeaFamily(familyId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["idea-families"] });
      queryClient.invalidateQueries({ queryKey: ["idea-families", variables.familyId] });
    },
  });
}

export function useDeleteIdeaFamily() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (familyId: number) => deleteIdeaFamily(familyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idea-families"] });
    },
  });
}

export function useAddRepositoryToFamily() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ familyId, repoId }: { familyId: number; repoId: number }) =>
      addRepositoryToFamily(familyId, repoId),
    onMutate: async ({ familyId }) => {
      await queryClient.cancelQueries({ queryKey: ["idea-families", familyId] });
      const previous = queryClient.getQueryData<IdeaFamilyDetail>(["idea-families", familyId]);
      if (previous) {
        queryClient.setQueryData<IdeaFamilyDetail>(["idea-families", familyId], {
          ...previous,
          member_count: previous.member_count + 1,
        });
      }
      return { previous };
    },
    onError: (_err, { familyId }, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["idea-families", familyId], context.previous);
      }
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["idea-families", variables.familyId] });
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useRemoveRepositoryFromFamily() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ familyId, repoId }: { familyId: number; repoId: number }) =>
      removeRepositoryFromFamily(familyId, repoId),
    onMutate: async ({ familyId }) => {
      await queryClient.cancelQueries({ queryKey: ["idea-families", familyId] });
      const previous = queryClient.getQueryData<IdeaFamilyDetail>(["idea-families", familyId]);
      if (previous) {
        queryClient.setQueryData<IdeaFamilyDetail>(["idea-families", familyId], {
          ...previous,
          member_count: Math.max(0, previous.member_count - 1),
        });
      }
      return { previous };
    },
    onError: (_err, { familyId }, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["idea-families", familyId], context.previous);
      }
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["idea-families", variables.familyId] });
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}
