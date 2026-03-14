import { Suspense } from "react";
import { RepositoriesCatalogClient } from "./RepositoriesCatalogClient";

export default function RepositoriesPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <RepositoriesCatalogClient />
    </Suspense>
  );
}
