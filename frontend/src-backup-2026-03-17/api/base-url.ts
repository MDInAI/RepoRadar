export function normalizeApiBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

export function getRequiredApiBaseUrl(
  envValue: string | undefined = process.env.NEXT_PUBLIC_API_URL,
): string {
  if (!envValue) {
    throw new Error("NEXT_PUBLIC_API_URL is required but not configured.");
  }
  return normalizeApiBaseUrl(envValue);
}
