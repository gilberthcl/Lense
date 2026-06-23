import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { GlobalJob, OllamaStatus } from "../../lib/types";
import { useToast } from "../Toast";
import { Badge, Button, Card, EmptyState, fmtBytes, fmtDate, PanelHeader, Spinner } from "../ui";

function OllamaCard() {
  const toast = useToast();
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);

  const refresh = () => {
    setLoading(true);
    api.ollamaStatus().then(setStatus).catch(() => setStatus(null)).finally(() => setLoading(false));
  };
  useEffect(() => {
    refresh();
  }, []);

  const stopAll = async () => {
    if (!window.confirm("Unload all models from memory and cancel any running analysis jobs? This frees RAM if your machine is bogged down."))
      return;
    setStopping(true);
    try {
      const r = await api.ollamaUnload();
      toast.success(`Stopped ${r.unloaded.length} model(s), cancelled ${r.cancelled_jobs} job(s).`);
      refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not reach Ollama.");
    } finally {
      setStopping(false);
    }
  };

  return (
    <Card className="mb-4">
      <PanelHeader
        title="Ollama Runtime"
        subtitle="Models loaded in memory — free RAM if the machine is slow"
        right={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={refresh} disabled={loading}>
              {loading ? <Spinner /> : "Refresh"}
            </Button>
            <Button variant="danger" onClick={stopAll} disabled={stopping}>
              {stopping ? <Spinner /> : "Stop models & cancel jobs"}
            </Button>
          </div>
        }
      />
      <div className="p-4 text-sm">
        {status === null ? (
          <span className="text-slate-500">Checking…</span>
        ) : !status.reachable ? (
          <Badge className="border border-red-800 bg-red-950 text-red-300">
            Unreachable at {status.base_url}
          </Badge>
        ) : status.models.length === 0 ? (
          <Badge className="border border-emerald-800 bg-emerald-950 text-emerald-300">
            ✓ Reachable · no models loaded
          </Badge>
        ) : (
          <div className="space-y-1.5">
            <Badge className="border border-indigo-800 bg-indigo-950 text-indigo-300">
              {status.models.length} model(s) loaded
            </Badge>
            <ul className="mt-1 space-y-1">
              {status.models.map((m) => (
                <li key={m.name} className="flex justify-between rounded border border-slate-800 bg-slate-950/40 px-3 py-1.5">
                  <span className="font-mono text-xs text-slate-200">{m.name}</span>
                  <span className="font-mono text-xs text-slate-500">{fmtBytes(m.size_vram || m.size)} in memory</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="mt-2 text-xs text-slate-600">
          For a full Ollama restart (kills genuinely stuck generations), run <code>lense ollama restart</code>.
        </p>
      </div>
    </Card>
  );
}

const STATUS_COLOR: Record<string, string> = {
  running: "border border-indigo-800 bg-indigo-950 text-indigo-300",
  queued: "border border-amber-800 bg-amber-950 text-amber-300",
  done: "border border-emerald-800 bg-emerald-950 text-emerald-300",
  error: "border border-red-800 bg-red-950 text-red-300",
  cancelled: "border border-slate-700 bg-slate-800 text-slate-400",
};

const PHASE_LABEL: Record<string, string> = {
  methodology: "Methodology",
  plan: "Analysis plan",
  analysis: "Dataset analysis",
};

const ACTIVE = new Set(["running", "queued"]);

export default function JobsPanel() {
  const toast = useToast();
  const [jobs, setJobs] = useState<GlobalJob[] | null>(null);
  const timer = useRef<number | null>(null);

  const load = () =>
    api.listAllJobs(false).then(setJobs).catch(() => setJobs([]));

  useEffect(() => {
    load();
    // Poll while there are active jobs so progress stays live.
    timer.current = window.setInterval(load, 2500);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, []);

  const cancel = async (j: GlobalJob) => {
    try {
      await api.cancelJob(j.id);
      toast.success("Cancellation requested.");
      load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Cancel failed.");
    }
  };

  const activeCount = (jobs ?? []).filter((j) => ACTIVE.has(j.status)).length;

  return (
    <>
      <OllamaCard />
      <Card>
      <PanelHeader
        title="AI Jobs"
        subtitle="Background analysis jobs across all clients — running first"
        right={
          <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
            {activeCount} active
          </Badge>
        }
      />
      <div className="p-4">
        {jobs === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : jobs.length === 0 ? (
          <EmptyState>No jobs yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-3 font-medium">Client / Hunt</th>
                  <th className="px-3 py-2 font-medium">Kind</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Progress</th>
                  <th className="px-3 py-2 font-medium">Model</th>
                  <th className="px-3 py-2 font-medium">Started</th>
                  <th className="py-2 pl-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} className="border-b border-slate-900 last:border-0">
                    <td className="py-2.5 pr-3">
                      <div className="text-slate-200">{j.tenant_name ?? `#${j.tenant_id}`}</div>
                      <div className="text-xs text-slate-500">{j.hunt_name ?? `hunt ${j.hunt_id}`}</div>
                    </td>
                    <td className="px-3 py-2.5 text-slate-300">{PHASE_LABEL[j.phase] ?? j.phase}</td>
                    <td className="px-3 py-2.5">
                      <Badge className={STATUS_COLOR[j.status] ?? STATUS_COLOR.cancelled}>{j.status}</Badge>
                    </td>
                    <td className="px-3 py-2.5">
                      {ACTIVE.has(j.status) ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded bg-slate-800">
                            <div className="h-full bg-indigo-500" style={{ width: `${Math.max(3, j.progress ?? 0)}%` }} />
                          </div>
                          <span className="font-mono text-xs text-slate-500">{j.progress ?? 0}%</span>
                        </div>
                      ) : (
                        <span className="font-mono text-xs text-slate-600">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-slate-400">{j.model ?? "—"}</td>
                    <td className="px-3 py-2.5 text-xs text-slate-500">{j.created_at ? fmtDate(j.created_at) : "—"}</td>
                    <td className="py-2.5 pl-3 text-right">
                      {ACTIVE.has(j.status) ? (
                        <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => cancel(j)}>
                          Cancel
                        </Button>
                      ) : (
                        <span className="text-xs text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      </Card>
    </>
  );
}
