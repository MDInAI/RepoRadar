import { getRequiredApiBaseUrl } from "./base-url";

export interface IdeaFamily {
  id: number;
  title: string;
  description: string | null;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface IdeaFamilyDetail {
  id: number;
  title: string;
  description: string | null;
  member_count: number;
  member_repository_ids: number[];
  created_at: string;
  updated_at: string;
}

export interface CreateIdeaFamilyRequest {
  title: string;
  description?: string | null;
}

export interface UpdateIdeaFamilyRequest {
  title?: string | null;
  description?: string | null;
}

const getBaseUrl = () => `${getRequiredApiBaseUrl()}/api/v1/idea-families`;

export async function fetchIdeaFamilies(): Promise<IdeaFamily[]> {
  const response = await fetch(getBaseUrl());
  if (!response.ok) {
    throw new Error(`Failed to fetch idea families: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchIdeaFamily(familyId: number): Promise<IdeaFamilyDetail> {
  const response = await fetch(`${getBaseUrl()}/${familyId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch idea family: ${response.statusText}`);
  }
  return response.json();
}

export async function createIdeaFamily(data: CreateIdeaFamilyRequest): Promise<IdeaFamily> {
  const response = await fetch(getBaseUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(`Failed to create idea family: ${response.statusText}`);
  }
  return response.json();
}

export async function updateIdeaFamily(
  familyId: number,
  data: UpdateIdeaFamilyRequest,
): Promise<IdeaFamily> {
  const response = await fetch(`${getBaseUrl()}/${familyId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(`Failed to update idea family: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteIdeaFamily(familyId: number): Promise<void> {
  const response = await fetch(`${getBaseUrl()}/${familyId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete idea family: ${response.statusText}`);
  }
}

export async function addRepositoryToFamily(
  familyId: number,
  repoId: number,
): Promise<void> {
  const response = await fetch(`${getBaseUrl()}/${familyId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ github_repository_id: repoId }),
  });
  if (!response.ok) {
    throw new Error(`Failed to add repository to family: ${response.statusText}`);
  }
}

export async function removeRepositoryFromFamily(
  familyId: number,
  repoId: number,
): Promise<void> {
  const response = await fetch(`${getBaseUrl()}/${familyId}/members/${repoId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to remove repository from family: ${response.statusText}`);
  }
}
