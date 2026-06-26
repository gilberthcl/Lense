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
  complexity?: { dataset: string; role?: string; level: string; reason?: string }[];
  phases?: { name: string; datasets?: string[]; focus?: string; rationale?: string }[];
  batching?: string;
  qa_plan?: string;
  post_analysis?: { stage: string; description?: string }[];
  [key: string]: unknown;
}

export interface OllamaStatus {
  reachable: boolean;
  base_url: string;
  models: { name: string; size_vram: number; size: number }[];
}

export interface DbHealth {
  counts: { clients: number; hunts: number; datasets: number; findings: number; jobs: number };
  orphan_files: { count: number; bytes: number; sample: string[] };
  missing_dataset_files: { id: number; filename: string; path: string }[];
  stuck_jobs: { id: number; phase: string; status: string; hunt_id: number }[];
  healthy: boolean;
}

export interface PlanState {
  status?: "draft" | "accepted" | string;
  feedback?: string | null;
  accepted_at?: string | null;
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
  plan_state?: PlanState | null;
  auto_correlate?: boolean;
  auto_qa?: boolean;
  kind?: string;   // live | training (W3)
  training_review?: TrainingReviewState | null;
  created_at: string;
}

// Training-hunt "what I learned" review (W3).
export interface TrainingPattern {
  name: string;
  signal: string;
  category: string;
  rationale: string;
}
export interface TrainingReviewReport {
  overview: string;
  patterns: TrainingPattern[];
  false_positive_lessons: string[];
  takeaways: string[];
}
export interface TrainingReviewState {
  report: TrainingReviewReport;
  disposition: "accepted" | "rejected" | null;
  feedback: string | null;
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
  single_model_pipeline?: boolean;
  num_predict?: number;
  keep_alive?: string;
  enable_reviewer?: boolean;
  enable_qa?: boolean;
  anonymize_training?: boolean;
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
  result?: Record<string, unknown> | null;
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
  disposition?: string | null;   // accepted | partial | rejected | added (W1)
  score?: number | null;         // operator 1–10 rating (W1)
  dataset_id?: number | null;
  entities?: Record<string, string[]> | null;
  time_range?: Record<string, unknown> | null;
  behavioral_context?: Record<string, unknown> | null;
  evidence_rows?: Record<string, unknown>[] | null;
  source_dataset?: string | null;
  enrichment?: { note?: string; corroborating_datasets?: { id: number; filename?: string | null }[] } | null;
  chain_id?: number | null;
  merged_into_id?: number | null;
  [key: string]: unknown;
}

// W2 missed-finding wizard result.
export interface MissedFindingResult {
  finding: Finding;
  why_missed?: string | null;
  lessons?: string | null;
}

// W3 batch finding import result.
export interface ImportFindingsResult {
  count: number;
  findings: Finding[];
}

// W4 all-stages learning summary.
export interface LearningSummaryStage {
  count: number;
  avg_score: number | null;
  dispositions: Record<string, number>;
  recent: { disposition?: string | null; score?: number | null; feedback?: string | null; summary?: string | null }[];
}
export interface LearningSummary {
  by_stage: Record<string, LearningSummaryStage>;
  total: number;
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

// Correlation-phase output: an attack-chain over >= 2 findings.
export interface IncidentMitreStep {
  tactic?: string;
  technique?: string;
  finding_ref?: string;
}
export interface IncidentTimelineStep {
  time?: string;
  event?: string;
  finding_ref?: string;
}
export interface Incident {
  id: number;
  title: string;
  narrative?: string | null;
  severity?: string | null;
  confidence?: string | null;
  mitre_chain?: IncidentMitreStep[] | null;
  timeline?: IncidentTimelineStep[] | null;
  finding_ids?: number[] | null;
  finding_refs?: (string | null)[];
  created_at?: string;
}
export interface IncidentResult {
  hunt_id?: number;
  incidents: Incident[];
}

export interface MergedFinding {
  finding_id: number;
  ref: string;
  title: string;
  into_ref?: string | null;
  into_title?: string | null;
}
export interface EnrichedFinding {
  ref: string;
  title: string;
  note?: string | null;
  corroborating_datasets?: { id: number; filename?: string | null }[] | null;
}
export interface CuratedFinding {
  id: number;
  ref: string;
  title: string;
  category: string | null;
  severity: string | null;
  enriched: boolean;
  in_chain: boolean;
  chain_id: number | null;
}
export interface CorrelationSummary {
  hunt_id?: number;
  totals: {
    findings: number;
    active_findings: number;
    incidents: number;
    merged: number;
    enriched: number;
  };
  incidents: Incident[];
  merged: MergedFinding[];
  enriched: EnrichedFinding[];
  curated?: CuratedFinding[];
}

// Analysis-phase summary report.
export interface AnalysisDatasetSummary {
  id: number;
  filename: string;
  status: string;
  row_count?: number;
  col_count?: number;
  assessment?: string | null;
  finding_count: number;
  findings: {
    ref: string;
    title: string;
    category?: FindingCategory;
    severity?: string | null;
    merged?: boolean;
  }[];
}
export interface AnalysisSummary {
  hunt_id?: number;
  totals: {
    datasets: number;
    analyzed: number;
    findings: number;
    active_findings: number;
    by_category: Record<string, number>;
    by_severity: Record<string, number>;
  };
  datasets: AnalysisDatasetSummary[];
}

// QA phase.
export interface QAStageCheck {
  stage: string;
  status: "pass" | "warn" | "fail";
  detail: string;
  fix?: string | null;
}
export interface QAIssueMeta {
  dataset_ids?: (number | null)[];
  dataset_names?: (string | null)[];
}
export interface QACriticalIssue {
  type: "stage" | "finding";
  stage?: string;
  finding_ref?: string;
  title?: string;
  detail?: string;
  fix?: string | null;
  meta?: QAIssueMeta;
}
export interface QAAction {
  action: string;
  finding_ref?: string;
  finding_id?: number;
  fields?: string[];
  before?: Record<string, unknown>;
  rolled_back?: boolean;
  detail?: string;
}
export interface QAReport {
  status: "passed" | "needs_attention" | "critical";
  stage_checks: QAStageCheck[];
  totals: {
    findings: number;
    avg_completeness: number;
    complete: number;
    incomplete: number;
    minor?: number;
    critical: number;
    judged?: number;
    gap_filled: number;
    activity?: string[];
  };
  critical_issues: QACriticalIssue[];
  actions: QAAction[];
  created_at?: string;
}
export interface QAFindingJudge {
  verdict?: string;
  missing?: string[];
  false_positive_risk?: string;
  severity_assessment?: string;
  suggested_fix?: string;
}
export interface QAFindingState {
  ref: string;
  title: string;
  category?: FindingCategory;
  severity?: string | null;
  qa?: {
    score?: number;
    status?: string;
    gaps?: string[];
    detail_gaps?: string[];
    mitre_issues?: string[];
    grounding_issues?: string[];
    judge?: QAFindingJudge;
  } | null;
}
export interface QAResult {
  hunt_id?: number;
  report: QAReport | null;
  findings: QAFindingState[];
}

// Per-tenant training-data export (LoRA fine-tuning, Phase 1).
export interface TrainingStats {
  tenant_id: number;
  total_findings: number;
  validated: number;
  rejected: number;
  eligible_positives: number;
  thin_validated_skipped: number;
  by_category: Record<string, number>;
  min_validated: number;
  ready_for_training: boolean;
  anonymized?: boolean;
  written?: {
    sft_examples: number;
    negative_examples: number;
    sft_path: string;
    negatives_path: string;
  };
}

// Golden-eval baseline (LoRA fine-tuning, Phase 2).
export interface EvalMetrics {
  cases: number;
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
  hallucination_rate: number;
  parse_error_rate: number;
  findings_produced: number;
}
export interface EvalCaseRow {
  name: string;
  source?: string;
  tp: number;
  fp: number;
  fn: number;
  n_expected: number;
  n_produced: number;
  hallucinated: number;
  parse_error?: boolean;
}
export interface EvalBaseline {
  status: "none" | "running" | "done" | "error";
  tenant_id?: number;
  model?: string | null;
  sources?: { synthetic: number; holdout: number };
  metrics?: EvalMetrics;
  cases?: EvalCaseRow[];
  created_at?: string;
  started_at?: string;
  include_holdout?: boolean;
  error?: string;
}

// Per-tenant fine-tuned model registry (LoRA fine-tuning, Phase 3).
export interface ModelComparison {
  deltas: Record<string, number>;
  regressed: boolean | null;
  tolerance: number;
}
export interface TenantModelInfo {
  id: number;
  tenant_id: number;
  base_model: string;
  ollama_model_name: string;
  version: number;
  status: "draft" | "validating" | "active" | "rejected" | "retired" | string;
  train_metrics?: Record<string, unknown> | null;
  eval_metrics?: EvalMetrics | null;
  baseline_metrics?: EvalMetrics | null;
  comparison?: ModelComparison | null;
  notes?: string | null;
  created_at?: string;
  trained_at?: string | null;
  activated_at?: string | null;
}
export interface TenantModelsList {
  active_model: string | null;
  models: TenantModelInfo[];
}
export interface AvailableModel {
  name: string;
  allowed: boolean;
  reason: string;
  assigned_to?: string | null;  // another client using this as its base
  locked?: boolean;             // unavailable here (assigned to another client)
}
export interface AvailableModels {
  reachable: boolean;
  default_model: string | null;
  current: string | null;       // tenant's chosen base, or null = global default
  models: AvailableModel[];
}
export interface TrainStatus {
  status: "none" | "running" | "done" | "error";
  step?: string;
  pct?: number;
  base_model?: string;
  log?: string[];
  error?: string;
  version?: number;
  ollama_model_name?: string;
  examples?: number;
}

// Tools — Data Sanitizer.
export interface SanitizeReplacement {
  value: string;
  placeholder: string;
  type: string;
  action: string;
}
export interface SanitizeUncertain {
  value: string;
  type: string;
  reason: string;
}
export interface SanitizeSummary {
  replaced: number;
  anonymized: number;
  redacted: number;
  kept: number;
  uncertain: number;
  by_type: Record<string, number>;
}
export interface SanitizeResult {
  sanitized: string;
  replacements: SanitizeReplacement[];
  kept: { value: string; reason: string }[];
  uncertain?: SanitizeUncertain[];
  summary?: SanitizeSummary;
  decoded?: { codec: string | null; changed: boolean };
  input?: string;
}
export type DecodeMode = "" | "auto" | "base64" | "hex" | "url";

// Accept/reject disposition — the model's reflection (lesson) when feedback given.
export interface DispositionReflection {
  lesson: string;
  reasoning: string | null;
}
export interface FindingDispositionResult {
  finding: Finding;
  reflection: DispositionReflection | null;
}

// Partial-accept regeneration — the visible outcome the analyst sees.
export interface RevisionChange {
  field: string;
  before: unknown;
  after: unknown;
}
export interface RevisionChecklistItem {
  point: string;
  addressed: boolean;
  how: string | null;
}
export interface FindingRevisionResult {
  finding: Finding;
  reasoning: string | null;
  addressed: RevisionChecklistItem[];
  changes: RevisionChange[];
  no_op: boolean;
}

// Model manager (global).
export interface CatalogModel {
  key: string;
  name: string;
  ref: string;
  params: string;
  approx_gb: number;
  origin: string;
  focus: string;
  kind: string;        // cyber | generalist | embed
  recommended: boolean;
  compliant: boolean;
  note: string;
}
export interface InstalledModel {
  name: string;
  size: number;
  allowed: boolean;
  reason: string;
  catalog: string | null;
  kind: string | null;
  protected: boolean;
  assigned_to: string | null;
  is_default: boolean;
}
export interface PullStatus {
  status: string;
  pct: number | null;
  done: boolean;
  error: string | null;
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
  kind?: string;   // live | training (W3)
}
