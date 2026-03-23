import { RepositoryDetailClient } from "@/components/repositories/RepositoryDetailClient";

export default async function RepositoriesDetailPage({
  params,
}: {
  params: Promise<{ repositoryId: string }> | { repositoryId: string };
}) {
  const resolvedParams = await Promise.resolve(params);
  const repositoryId = Number.parseInt(resolvedParams.repositoryId, 10);
  return <RepositoryDetailClient repositoryId={repositoryId} />;
}
