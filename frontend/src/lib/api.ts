// Typed fetch client for the Threat Hunt Findings Engine backend.
import type {
  CategoryDef,
  CorrelationResult,
  CreateHuntInput,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
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

  // --- Tenants ---
  listTenants: () => request<Tenant[]>("/api/tenants"),
  createTenant: (body: CreateTenantInput) =>
    request<Tenant>("/api/tenants", { method: "POST", body: JSON.stringify(body) }),
  getTenant: (tid: string) => request<Tenant>(`/api/tenants/${tid}`),

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
  getJob: (tid: string, hid: string, jobId: string) =>
    request<Job>(`/api/tenants/${tid}/hunts/${hid}/jobs/${jobId}`),

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

  // --- Report (Phase 2): download the generated DOCX ---
  downloadReport: async (tid: string, hid: string, lang: ReportLang = "en") => {
    const path = `/api/tenants/${tid}/hunts/${hid}/report?lang=${lang}`;
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}`, { headers: { Accept: "*/*" } });
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
