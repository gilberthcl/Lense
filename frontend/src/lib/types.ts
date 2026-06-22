// Centralized type definitions mirroring the backend API contract.

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  context_notes?: string | null;
  created_at: string;
}

export type DocType =
  | "methodology"
  | "finding_categories"
  | "finding_format"
  | "approved_software"
  | "report_standard"
  | "previous_report"
  | "validated_finding";

export interface KnowledgeDoc {
  id: string;
  tenant_id: string;
  doc_type: DocType;
  title: string;
  content?: string;
  created_at: string;
}

export type HuntStatus = string;

export interface MethodologyTopic {
  number?: string;
  name?: string;
  objective?: string;
  mitre?: string[];
  expected_benign?: string;
  malicious_indicators?: string;
}

export interface MethodologyBrief {
  hunt_overview?: string;
  scope?: string;
  topics?: MethodologyTopic[];
  executed_queries?: { topic?: string; summary?: string; had_results?: boolean }[];
  known_false_positives?: string[];
  what_to_expect?: string;
  note?: string;
  [key: string]: unknown;
}

export interface Hunt {
  id: string;
  tenant_id: string;
  name: string;
  objective?: string | null;
  status: HuntStatus;
  report_language?: string;
  edr?: string | null;
  siem?: string | null;
  methodology_text?: string | null;
  methodology_brief?: MethodologyBrief | null;
  created_at: string;
}

// Global module configuration (Structured Threat Hunt)
export interface ModuleConfig {
  id: number;
  module: string;
  key: string;
  title: string;
  content: string;
  updated_at: string;
}

export interface CategoryDef {
  key: string;
  label_en: string;
  label_es: string;
  definition: string;
  color: string;
}

export interface AiEngineConfig {
  base_url: string;
  analyst_model: string;
  reviewer_model: string;
  qa_model: string;
  embed_model: string;
  temperature: number;
  timeout: number;
}

export interface PlatformConfig {
  platform_name: string;
  default_report_language: string;
}

export interface GlobalConfig {
  ai_engine: AiEngineConfig;
  ai_defaults: AiEngineConfig;
  platform: PlatformConfig;
}

// Client portal overview (aggregated)
export interface ClientOverview {
  client: { id: number; name: string; slug: string };
  counts: { hunts: number; datasets: number; findings: number; validated: number };
  risk: { score: number; label: string };
  by_category: { key: string; label: string; count: number }[];
  by_status: Record<string, number>;
  recent_hunts: {
    id: number;
    name: string;
    status: string;
    report_language?: string;
    edr?: string | null;
    siem?: string | null;
    created_at?: string | null;
  }[];
  recent_findings: {
    id: number;
    finding_ref: string;
    title: string;
    category: string;
    severity?: string | null;
    status: string;
    hunt_id: number;
    created_at?: string | null;
  }[];
}

export type DatasetStatus = "uploaded" | "analyzing" | "analyzed" | "error" | string;

export interface Dataset {
  id: string;
  filename: string;
  file_size: number;
  row_count: number;
  col_count: number;
  status: DatasetStatus;
  created_at: string;
}

export type JobStatus = "queued" | "running" | "done" | "error" | string;

export interface Job {
  id: string;
  phase?: string;
  status: JobStatus;
  progress?: number; // 0..100
  current_task?: string | null;
  error?: string | null;
}

export type FindingCategory =
  | "malicious"
  | "suspicious"
  | "risky"
  | "policy_violation"
  | "unconfirmed"
  | string;

export type FindingStatus = "draft" | "validated" | "rejected";

export interface Finding {
  id: string;
  finding_ref: string;
  title: string;
  category: FindingCategory;
  severity?: string | null;
  confidence?: string | number | null;
  summary?: string | null;
  evidence?: unknown;
  mitre?: unknown;
  affected_assets?: unknown;
  affected_users?: unknown;
  recommendations?: unknown;
  status: FindingStatus;
  reviewer_notes?: string | null;
  [key: string]: unknown;
}

// --- Correlations (Phase 2) ---
export type EntityType = "host" | "user" | "ip" | "hash" | "domain" | string;

export interface CorrelationFindingRef {
  finding_id?: number;
  finding_ref?: string;
  title?: string;
  category?: FindingCategory;
  dataset_id?: number;
  dataset_name?: string | null;
}

export interface CorrelationEntity {
  entity_type: EntityType;
  value: string;
  dataset_count: number;
  finding_count: number;
  datasets: { dataset_id: number; filename?: string | null }[];
  categories: FindingCategory[];
  max_category: FindingCategory;
  findings: CorrelationFindingRef[];
}

export interface CorrelationResult {
  hunt_id?: number;
  entity_count: number;
  correlations: CorrelationEntity[];
  iocs: CorrelationEntity[];
}

export type ReportLang = "en" | "es";

// Request payload helpers
export interface CreateTenantInput {
  name: string;
  slug: string;
  context_notes?: string;
}

export interface CreateKnowledgeInput {
  doc_type: DocType;
  title: string;
  content: string;
}

export interface CreateHuntInput {
  name: string;
  objective?: string;
  methodology_text?: string;
  report_language?: string;
  edr?: string;
  siem?: string;
}
