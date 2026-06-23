// Centralized type definitions mirroring the backend API contract.

export interface Stakeholder {
  name?: string;
  title?: string;
  email?: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  context_notes?: string | null;
  sector?: string | null;
  industries?: string[] | null;
  country?: string | null;
  city?: string | null;
  is_global?: boolean;
  internal_domain?: string | null;
  edr_platform?: string | null;
  siem_platform?: string | null;
  xdr_platform?: string | null;
  other_tech?: string | null;
  dpe_name?: string | null;
  dpe_email?: string | null;
  pm_name?: string | null;
  pm_email?: string | null;
  acct_other_name?: string | null;
  acct_other_role?: string | null;
  acct_other_email?: string | null;
  stakeholders?: Stakeholder[] | null;
  contracted_services?: string[] | null;
  sla_hours?: number;
  hunt_maturity?: number;
  logo_path?: string | null;
  contract_path?: string | null;
  contract_start?: string | null;
  contract_end?: string | null;
  created_at: string;
}

export interface Contact {
  id: number;
  tenant_id: number;
  name: string;
  title?: string | null;
  email?: string | null;
  phone?: string | null;
  is_primary: boolean;
  created_at: string;
}

export interface CreateContactInput {
  name: string;
  title?: string;
  email?: string;
  phone?: string;
  is_primary?: boolean;
}

export type CalendarEventType =
  | "pre_hunt"
  | "hunt"
  | "post_hunt"
  | "planning"
  | "review"
  | "other";

export interface CalendarEvent {
  id: number;
  tenant_id: number;
  title: string;
  event_type: CalendarEventType | string;
  event_date?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface CreateCalendarInput {
  title: string;
  event_type: string;
  event_date?: string;
  notes?: string;
}

export interface ApprovedSoftware {
  id: number;
  tenant_id: number;
  name: string;
  vendor?: string | null;
  category?: string | null;
  notes?: string | null;
  is_approved: boolean;
  created_at: string;
}

export interface CreateApprovedSoftwareInput {
  name: string;
  vendor?: string;
  category?: string;
  notes?: string;
  is_approved?: boolean;
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

// Deterministically-parsed methodology sections (the 3 sub-tabs).
export interface MitreCoverage {
  technique: string;
  tactic: string;
}
export interface PlanTopic {
  name: string;
  mitre?: string;
  indicators: string[];
}
export interface QueryRow {
  name: string;
  query: string;
  outcome: string;
  result_count: number | null;
  status: "results" | "no_results" | "pending" | "unknown" | string;
}
export interface QueryTopic {
  number: number;
  name: string;
  mitre: string;
  rows: QueryRow[];
}
export interface MethodologySections {
  available: boolean;
  mitre_coverage?: MitreCoverage[];
  description?: string;
  plan_of_action?: { intro: string; topics: PlanTopic[]; closing: string };
  queries?: QueryTopic[];
  stats?: { topic_count: number; query_count: number; queries_with_results: number };
}

export interface AnalysisPlan {
  summary?: string;
  estimated_rounds?: number;
  complexity?: { dataset: string; level: string; reason?: string }[];
  phases?: { name: string; datasets?: string[]; focus?: string; rationale?: string }[];
  batching?: string;
  qa_plan?: string;
  [key: string]: unknown;
}

export interface DbHealth {
  counts: { clients: number; hunts: number; datasets: number; findings: number; jobs: number };
  orphan_files: { count: number; bytes: number; sample: string[] };
  missing_dataset_files: { id: number; filename: string; path: string }[];
  stuck_jobs: { id: number; phase: string; status: string; hunt_id: number }[];
  healthy: boolean;
}

export interface DatasetPreview {
  filename: string;
  row_count: number;
  col_count: number;
  columns: string[];
  rows: string[][];
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
  methodology_sections?: MethodologySections | null;
  analysis_plan?: AnalysisPlan | null;
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
  logo_path?: string | null;
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

export interface JobLogEntry {
  at: number; // seconds since job start
  msg: string;
}

export interface GlobalJob {
  id: number;
  tenant_id: number;
  tenant_name?: string | null;
  hunt_id: number;
  hunt_name?: string | null;
  dataset_id?: number | null;
  phase: string;
  status: JobStatus;
  progress?: number;
  current_task?: string | null;
  model?: string | null;
  error?: string | null;
  created_at?: string | null;
}

export interface Job {
  id: string;
  phase?: string;
  dataset_id?: number | null;
  status: JobStatus;
  progress?: number; // 0..100
  current_task?: string | null;
  model?: string | null;
  log?: JobLogEntry[] | null;
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
  sector?: string;
  industries?: string[];
  country?: string;
  city?: string;
  is_global?: boolean;
  internal_domain?: string;
  edr_platform?: string;
  siem_platform?: string;
  xdr_platform?: string;
  other_tech?: string;
  dpe_name?: string;
  dpe_email?: string;
  pm_name?: string;
  pm_email?: string;
  acct_other_name?: string;
  acct_other_role?: string;
  acct_other_email?: string;
  stakeholders?: Stakeholder[];
  contracted_services?: string[];
  sla_hours?: number;
  hunt_maturity?: number;
  contract_start?: string;
  contract_end?: string;
}

export type UpdateTenantInput = Partial<CreateTenantInput> & { name?: string };

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
