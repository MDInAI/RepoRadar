export const settingsContractEndpoints = {
  summary: "/api/v1/settings/summary",
} as const;

export type SettingsOwner =
  | "agentic-workflow"
  | "gateway"
  | "openclaw"
  | "workspace";
export type SettingsAccess =
  | "project-owned"
  | "read-only-reference"
  | "gateway-managed";
export type ValidationSeverity = "error" | "warning";

export interface ConfigurationOwnership {
  key: string;
  owner: SettingsOwner;
  access: SettingsAccess;
  source: string;
  description: string;
  surfaces: string[];
  notes: string[];
}

export interface MaskedSettingSummary {
  key: string;
  label: string;
  owner: SettingsOwner;
  source: string;
  configured: boolean;
  required: boolean;
  secret: boolean;
  value: string | null;
  notes: string[];
}

export interface ConfigurationValidationIssue {
  severity: ValidationSeverity;
  field: string;
  owner: SettingsOwner;
  code: string;
  message: string;
  source: string;
}

export interface ConfigurationValidationResult {
  valid: boolean;
  issues: ConfigurationValidationIssue[];
}

export interface SettingsSummaryResponse {
  contract_version: string;
  ownership: ConfigurationOwnership[];
  project_settings: MaskedSettingSummary[];
  worker_settings: MaskedSettingSummary[];
  openclaw_settings: MaskedSettingSummary[];
  validation: ConfigurationValidationResult;
}

export const settingsOwnershipHighlights = [
  {
    title: "OpenClaw-native config",
    body: "OpenClaw keeps ownership of gateway auth, channel definitions, and default model conventions in ~/.openclaw/openclaw.json.",
  },
  {
    title: "Gateway transport",
    body: "Gateway connection details are normalized by backend services and exposed only as masked summaries.",
  },
  {
    title: "Project runtime",
    body: "Agentic-Workflow owns local runtime paths, provider credentials, and pacing thresholds in project env files.",
  },
] as const;
