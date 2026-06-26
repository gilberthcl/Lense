// Typed fetch client for the Threat Hunt Findings Engine backend.
import type {
  AiEngineConfig,
  ApprovedSoftware,
  CalendarEvent,
  CategoryDef,
  ClientOverview,
  Contact,
  CorrelationResult,
  CorrelationSummary,
  AnalysisSummary,
  QAResult,
  IncidentResult,
  CreateApprovedSoftwareInput,
  CreateCalendarInput,
  CreateContactInput,
  CreateHuntInput,
  DatasetPreview,
  DbHealth,
  GlobalConfig,
  GlobalJob,
  OllamaStatus,
  PlatformConfig,
  UpdateTenantInput,
  CreateKnowledgeInput,
  CreateTenantInput,
  Dataset,
  Finding,
  FindingStatus,
  Hunt,
  Job,
  KnowledgeDoc,
  ModuleConfig,
  ReportLang,
  Tenant,
  TrainingStats,
  EvalBaseline,
  TenantModelsList,
  TenantModelInfo,
  MissedFindingResult,
  ImportFindingsResult,
  AvailableModels,
} from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// --- Access token (local PIN) ---
const TOKEN_KEY = "lens-token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// Fired when the session is no longer authenticated. The PIN gate listens for
// this and re-locks via React state — deliberately NOT a full-page reload,
// which would loop forever (and thrash the browser) if a protected call keeps
// 401ing while the page is loading.
export const AUTH_LOST_EVENT = "lens:auth-lost";
export function signalAuthLost() {
  clearToken();
  window.dispatchEvent(new CustomEvent(AUTH_LOST_EVENT));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const token = getToken();
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    throw new ApiError(
      `Network error contacting ${API_BASE}${path}. Is the backend running?`,
      0,
      e,
    );
  }

  // The PIN became invalid (e.g. changed elsewhere, or the backend was reset
  // by a fresh `lense up` so a stale token no longer verifies). Drop it and
  // re-gate through the PIN screen WITHOUT reloading — a reload here would
  // re-issue the same protected call, 401 again, and loop the browser to death.
  if (res.status === 401 && !path.startsWith("/api/auth")) {
    signalAuthLost();
  }

  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : undefined) ?? `Request failed (${res.status})`;
    throw new ApiError(detail, res.status, data);
  }

  return data as T;
}

export interface Health {
  status: string;
  service: string;
}

export const api = {
  // --- Health ---
  health: () => request<Health>("/api/health"),

  // --- Auth (local access PIN) ---
  authStatus: () => request<{ configured: boolean }>("/api/auth/status"),
  authSetup: (pin: string) =>
    request<{ token: string }>("/api/auth/setup", {
      method: "POST",
      body: JSON.stringify({ pin }),
    }),
  authLogin: (pin: string) =>
    request<{ token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ pin }),
    }),
  authChange: (current_pin: string, new_pin: string) =>
    request<{ token: string }>("/api/auth/change", {
      method: "POST",
      body: JSON.stringify({ current_pin, new_pin }),
    }),

  // --- Platform logo ---
  platformLogoUrl: () => `${API_BASE}/api/config/platform/logo`,
  uploadPlatformLogo: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<PlatformConfig>("/api/config/platform/logo", { method: "POST", body: fd });
  },

  // --- Tenants ---
  listTenants: () => request<Tenant[]>("/api/tenants"),
  createTenant: (body: CreateTenantInput) =>
    request<Tenant>("/api/tenants", { method: "POST", body: JSON.stringify(body) }),
  getTenant: (tid: string) => request<Tenant>(`/api/tenants/${tid}`),
  updateClient: (tid: string, body: UpdateTenantInput) =>
    request<Tenant>(`/api/tenants/${tid}`, { method: "PUT", body: JSON.stringify(body) }),
  getClientOverview: (tid: string) =>
    request<ClientOverview>(`/api/tenants/${tid}/overview`),
  logoUrl: (tid: string) => `${API_BASE}/api/tenants/${tid}/logo`,
  contractUrl: (tid: string) => `${API_BASE}/api/tenants/${tid}/contract`,
  uploadLogo: (tid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Tenant>(`/api/tenants/${tid}/logo`, { method: "POST", body: fd });
  },
  uploadContract: (tid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Tenant>(`/api/tenants/${tid}/contract`, { method: "POST", body: fd });
  },

  // --- Contacts ---
  listContacts: (tid: string) => request<Contact[]>(`/api/tenants/${tid}/contacts`),
  createContact: (tid: string, body: CreateContactInput) =>
    request<Contact>(`/api/tenants/${tid}/contacts`, { method: "POST", body: JSON.stringify(body) }),
  deleteContact: (tid: string, cid: number) =>
    request<void>(`/api/tenants/${tid}/contacts/${cid}`, { method: "DELETE" }),

  // --- Calendar ---
  listCalendar: (tid: string) => request<CalendarEvent[]>(`/api/tenants/${tid}/calendar`),
  createEvent: (tid: string, body: CreateCalendarInput) =>
    request<CalendarEvent>(`/api/tenants/${tid}/calendar`, { method: "POST", body: JSON.stringify(body) }),
  deleteEvent: (tid: string, eid: number) =>
    request<void>(`/api/tenants/${tid}/calendar/${eid}`, { method: "DELETE" }),

  // --- Approved software (environment baseline) ---
  listApprovedSoftware: (tid: string) =>
    request<ApprovedSoftware[]>(`/api/tenants/${tid}/approved-software`),
  createApprovedSoftware: (tid: string, body: CreateApprovedSoftwareInput) =>
    request<ApprovedSoftware>(`/api/tenants/${tid}/approved-software`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  bulkApprovedSoftware: (tid: string, names: string[], is_approved = true) =>
    request<ApprovedSoftware[]>(`/api/tenants/${tid}/approved-software/bulk`, {
      method: "POST",
      body: JSON.stringify({ names, is_approved }),
    }),
  deleteApprovedSoftware: (tid: string, sid: number) =>
    request<void>(`/api/tenants/${tid}/approved-software/${sid}`, { method: "DELETE" }),

  // --- Knowledge base ---
  listKnowledge: (tid: string) =>
    request<KnowledgeDoc[]>(`/api/tenants/${tid}/knowledge`),
  createKnowledge: (tid: string, body: CreateKnowledgeInput) =>
    request<KnowledgeDoc>(`/api/tenants/${tid}/knowledge`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteKnowledge: (tid: string, docId: string) =>
    request<void>(`/api/tenants/${tid}/knowledge/${docId}`, { method: "DELETE" }),

  // --- Hunts ---
  listHunts: (tid: string) => request<Hunt[]>(`/api/tenants/${tid}/hunts`),
  createHunt: (tid: string, body: CreateHuntInput) =>
    request<Hunt>(`/api/tenants/${tid}/hunts`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getHunt: (tid: string, hid: string) =>
    request<Hunt>(`/api/tenants/${tid}/hunts/${hid}`),
  deleteHunt: (tid: string, hid: string) =>
    request<void>(`/api/tenants/${tid}/hunts/${hid}`, { method: "DELETE" }),
  uploadMethodology: (tid: string, hid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Hunt>(`/api/tenants/${tid}/hunts/${hid}/methodology`, {
      method: "POST",
      body: fd,
    });
  },
  analyzeMethodology: (tid: string, hid: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/methodology/analyze`, {
      method: "POST",
    }),

  // --- Global module configuration (Structured Threat Hunt) ---
  listConfig: () =>
    request<ModuleConfig[]>("/api/config/structured-threat-hunt"),
  listCategories: () =>
    request<{ categories: CategoryDef[] }>(
      "/api/config/structured-threat-hunt/categories",
    ),

  // --- Global config (platform + AI engine) ---
  getGlobalConfig: () => request<GlobalConfig>("/api/config/global"),
  updateAiEngine: (patch: Partial<AiEngineConfig>) =>
    request<AiEngineConfig>("/api/config/global/ai-engine", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  updatePlatform: (patch: Partial<PlatformConfig>) =>
    request<PlatformConfig>("/api/config/global/platform", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  updateConfig: (key: string, content: string) =>
    request<ModuleConfig>(`/api/config/structured-threat-hunt/${key}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),

  // --- Datasets ---
  listDatasets: (tid: string, hid: string) =>
    request<Dataset[]>(`/api/tenants/${tid}/hunts/${hid}/datasets`),
  uploadDataset: (tid: string, hid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Dataset>(`/api/tenants/${tid}/hunts/${hid}/datasets`, {
      method: "POST",
      body: fd,
    });
  },
  analyzeDataset: (tid: string, hid: string, did: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/datasets/${did}/analyze`, {
      method: "POST",
    }),
  previewDataset: (tid: string, hid: string, did: string) =>
    request<DatasetPreview>(`/api/tenants/${tid}/hunts/${hid}/datasets/${did}/preview`),
  analysisPlan: (tid: string, hid: string, feedback?: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/analysis-plan`, {
      method: "POST",
      body: JSON.stringify({ feedback: feedback ?? null }),
    }),
  acceptPlan: (tid: string, hid: string) =>
    request<Hunt>(`/api/tenants/${tid}/hunts/${hid}/plan/accept`, { method: "POST" }),
  deletePlan: (tid: string, hid: string) =>
    request<Hunt>(`/api/tenants/${tid}/hunts/${hid}/plan/delete`, { method: "POST" }),
  resetAnalysis: (tid: string, hid: string) =>
    request<{ findings_deleted: number; datasets_reset: number }>(
      `/api/tenants/${tid}/hunts/${hid}/analysis/reset`,
      { method: "POST" },
    ),
  getJob: (tid: string, hid: string, jobId: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/jobs/${jobId}`),
  listHuntJobs: (tid: string, hid: string) =>
    request<Job[]>(`/api/tenants/${tid}/hunts/${hid}/jobs`),
  cancelHuntJob: (tid: string, hid: string, jobId: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/jobs/${jobId}/cancel`, { method: "POST" }),

  // --- Global jobs (Config → Jobs) ---
  listAllJobs: (active = false) =>
    request<GlobalJob[]>(`/api/jobs?active=${active}`),
  cancelJob: (jobId: number) =>
    request<{ id: number; status: string }>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
  ollamaModels: () =>
    request<{ models: string[]; reachable: boolean }>(`/api/config/ollama-models`),
  ollamaStatus: () => request<OllamaStatus>(`/api/config/ollama-status`),
  ollamaUnload: () =>
    request<{ unloaded: string[]; cancelled_jobs: number }>(`/api/config/ollama-unload`, {
      method: "POST",
    }),

  // --- DB / storage maintenance ---
  dbHealthScan: () => request<DbHealth>(`/api/config/db-health`),
  dbHealthClean: () =>
    request<{ removed_files: number; freed_bytes: number; cleared_jobs: number }>(
      `/api/config/db-health/clean`,
      { method: "POST" },
    ),

  // --- Findings ---
  listFindings: (tid: string, hid: string) =>
    request<Finding[]>(`/api/tenants/${tid}/hunts/${hid}/findings`),
  patchFinding: (
    tid: string,
    hid: string,
    fid: string,
    body: { status?: FindingStatus; reviewer_notes?: string },
  ) =>
    request<Finding>(`/api/tenants/${tid}/hunts/${hid}/findings/${fid}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteFinding: (tid: string, hid: string, fid: string) =>
    request<void>(`/api/tenants/${tid}/hunts/${hid}/findings/${fid}`, { method: "DELETE" }),
  // W1 rich disposition: accept | reject | partial, with optional score + feedback.
  dispositionFinding: (
    tid: string,
    hid: string,
    fid: string,
    body: { action: "accept" | "reject" | "partial"; feedback?: string; score?: number },
  ) =>
    request<Finding>(`/api/tenants/${tid}/hunts/${hid}/findings/${fid}/disposition`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  regenerateFinding: (tid: string, hid: string, fid: string, feedback: string) =>
    request<Finding>(`/api/tenants/${tid}/hunts/${hid}/findings/${fid}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  // W2 missed-finding wizard (false-negative capture).
  addMissedFinding: (tid: string, hid: string, dataset_id: string, description: string) =>
    request<MissedFindingResult>(`/api/tenants/${tid}/hunts/${hid}/findings/missed`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: Number(dataset_id), description }),
    }),
  addMissedContext: (tid: string, hid: string, fid: string, text: string) =>
    request<Finding>(`/api/tenants/${tid}/hunts/${hid}/findings/${fid}/missed-context`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  importFindings: (tid: string, hid: string, dataset_id: string, text: string) =>
    request<ImportFindingsResult>(`/api/tenants/${tid}/hunts/${hid}/findings/import`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: Number(dataset_id), text }),
    }),
  bulkPatchFindings: (
    tid: string,
    hid: string,
    finding_ids: string[],
    status: FindingStatus,
  ) =>
    request<Finding[]>(`/api/tenants/${tid}/hunts/${hid}/findings`, {
      method: "PATCH",
      body: JSON.stringify({ finding_ids: finding_ids.map(Number), status }),
    }),

  // --- Correlations (Phase 2) ---
  getCorrelations: (tid: string, hid: string) =>
    request<CorrelationResult>(`/api/tenants/${tid}/hunts/${hid}/correlations`),

  // --- Correlation phase (incidents / attack-chains) ---
  getIncidents: (tid: string, hid: string) =>
    request<IncidentResult>(`/api/tenants/${tid}/hunts/${hid}/correlations/incidents`),
  getCorrelationSummary: (tid: string, hid: string) =>
    request<CorrelationSummary>(`/api/tenants/${tid}/hunts/${hid}/correlations/summary`),
  unmergeFinding: (tid: string, hid: string, fid: number) =>
    request<{ ok: boolean }>(
      `/api/tenants/${tid}/hunts/${hid}/correlations/findings/${fid}/unmerge`,
      { method: "POST" },
    ),
  getAnalysisSummary: (tid: string, hid: string) =>
    request<AnalysisSummary>(`/api/tenants/${tid}/hunts/${hid}/analysis-summary`),
  runCorrelation: (tid: string, hid: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/correlations/run`, { method: "POST" }),

  // --- QA phase ---
  getQA: (tid: string, hid: string) =>
    request<QAResult>(`/api/tenants/${tid}/hunts/${hid}/qa`),
  runQA: (tid: string, hid: string, feedback?: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/qa/run`, {
      method: "POST",
      body: JSON.stringify({ feedback: feedback ?? null }),
    }),
  setAutoQa: (tid: string, hid: string, value: boolean) =>
    request<Hunt>(`/api/tenants/${tid}/hunts/${hid}`, {
      method: "PATCH",
      body: JSON.stringify({ auto_qa: value }),
    }),
  rollbackQA: (tid: string, hid: string) =>
    request<{ reverted_findings: number; reverted_fields: number }>(
      `/api/tenants/${tid}/hunts/${hid}/qa/rollback`,
      { method: "POST" },
    ),

  // --- Per-tenant training data (LoRA fine-tuning, Phase 1) ---
  getTrainingStats: (tid: string) =>
    request<TrainingStats>(`/api/tenants/${tid}/training/stats`),
  exportTrainingSet: (tid: string) =>
    request<TrainingStats>(`/api/tenants/${tid}/training/export`, { method: "POST" }),

  // --- Golden-eval baseline (LoRA fine-tuning, Phase 2) ---
  getEvalBaseline: (tid: string) =>
    request<EvalBaseline>(`/api/tenants/${tid}/eval/baseline`),
  runEval: (tid: string, includeHoldout: boolean) =>
    request<{ status: string }>(
      `/api/tenants/${tid}/eval/run?include_holdout=${includeHoldout}`,
      { method: "POST" },
    ),

  // --- Per-tenant fine-tuned model registry (LoRA fine-tuning, Phase 3) ---
  getTenantModels: (tid: string) =>
    request<TenantModelsList>(`/api/tenants/${tid}/models`),
  getAvailableModels: (tid: string) =>
    request<AvailableModels>(`/api/tenants/${tid}/models/available`),
  setBaseModel: (tid: string, model: string | null) =>
    request<{ current: string | null; default_model: string | null; warning: string | null }>(
      `/api/tenants/${tid}/models/base`,
      { method: "POST", body: JSON.stringify({ model }) },
    ),
  evaluateModel: (tid: string, id: number, includeHoldout: boolean) =>
    request<{ status: string }>(
      `/api/tenants/${tid}/models/${id}/evaluate?include_holdout=${includeHoldout}`,
      { method: "POST" },
    ),
  promoteModel: (tid: string, id: number) =>
    request<TenantModelInfo>(`/api/tenants/${tid}/models/${id}/promote`, { method: "POST" }),
  rejectModel: (tid: string, id: number) =>
    request<TenantModelInfo>(`/api/tenants/${tid}/models/${id}/reject`, { method: "POST" }),
  setAutoCorrelate: (tid: string, hid: string, value: boolean) =>
    request<Hunt>(`/api/tenants/${tid}/hunts/${hid}`, {
      method: "PATCH",
      body: JSON.stringify({ auto_correlate: value }),
    }),

  // --- Report (Phase 2): download the generated DOCX ---
  downloadReport: async (tid: string, hid: string, lang: ReportLang = "en") => {
    const path = `/api/tenants/${tid}/hunts/${hid}/report?lang=${lang}`;
    const token = getToken();
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}`, {
        headers: { Accept: "*/*", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
    } catch (e) {
      throw new ApiError(`Network error contacting ${API_BASE}${path}.`, 0, e);
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let detail = `Report failed (${res.status})`;
      try {
        const j = JSON.parse(text);
        if (j && typeof j === "object" && "detail" in j) detail = String(j.detail);
      } catch {
        /* non-JSON body */
      }
      throw new ApiError(detail, res.status, text);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match?.[1] ?? `lens_report_${hid}_${lang}.docx`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};

// Poll a job until it reaches a terminal state.
export async function pollJob(
  tid: string,
  hid: string,
  jobId: string,
  onProgress: (job: Job) => void,
  intervalMs = 1200,
): Promise<Job> {
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await api.getJob(tid, hid, jobId);
    onProgress(job);
    if (job.status === "done" || job.status === "error") {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
