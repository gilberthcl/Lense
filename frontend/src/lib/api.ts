// Typed fetch client for the Threat Hunt Findings Engine backend.
import type {
  CreateHuntInput,
  CreateKnowledgeInput,
  CreateTenantInput,
  Dataset,
  Finding,
  FindingStatus,
  Hunt,
  Job,
  KnowledgeDoc,
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
  patchFinding: (tid: string, hid: string, fid: string, status: FindingStatus) =>
    request<Finding>(`/api/tenants/${tid}/hunts/${hid}/findings/${fid}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
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
