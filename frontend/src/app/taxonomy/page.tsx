import { Suspense } from "react";

import { TaxonomyQaClient } from "./TaxonomyQaClient";

export default function TaxonomyQaPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <TaxonomyQaClient />
    </Suspense>
  );
}
