export const APP_TIME_ZONE = "Asia/Jerusalem";

const APP_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  timeZone: APP_TIME_ZONE,
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZoneName: "short",
});

export function formatAppDateTime(value: string | Date | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }

  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }

  return APP_DATE_TIME_FORMATTER.format(parsed);
}
