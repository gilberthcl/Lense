import { Fragment, useEffect, useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type {
  CorrelationEntity,
  CorrelationResult,
  Hunt,
  Incident,
  Job,
} from "../lib/types";
import { useToast } from "./Toast";
import {
  Button,
  Card,
  CategoryBadge,
  EmptyState,
  PanelHeader,
  Spinner,
} from "./ui";

const ENTITY_LABEL: Record<string, string> = {
  host: "Host",
  user: "User",
  ip: "IP",
  hash: "Hash",
  domain: "Domain",
};

const SEV_COLOR: Record<string, string> = {
  critical: "bg-rose-900/60 text-rose-200",
  high: "bg-orange-900/60 text-orange-200",
  medium: "bg-amber-900/50 text-amber-200",
  low: "bg-sky-900/50 text-sky-200",
  informational: "bg-slate-800 text-slate-300",
};

function SeverityBadge({ value }: { value?: string | null }) {
  if (!value) return null;
  const cls = SEV_COLOR[value.toLowerCase()] ?? "bg-slate-800 text-slate-300";
  return (
    <span className={`rounded px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {value}
    </span>
  );
}

function EntityTypeBadge({ type }: { type: string }) {
  return (
    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide text-slate-300">
      {ENTITY_LABEL[type] ?? type}
    </span>
  );
}

function IncidentCard({ incident }: { incident: Incident }) {
  const refs = (incident.finding_refs ?? []).filter(Boolean) as string[];
  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-100">{incident.title}</span>
        <SeverityBadge value={incident.severity} />
        {incident.confidence && (
          <span className="text-[11px] text-slate-500">confidence: {incident.confidence}</span>
        )}
      </div>
      {incident.narrative && (
        <p className="mt-2 text-sm leading-relaxed text-slate-300">{incident.narrative}</p>
      )}

      {incident.mitre_chain && incident.mitre_chain.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Attack chain
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            {incident.mitre_chain.map((step, i) => (
              <Fragment key={i}>
                {i > 0 && <span className="text-slate-600">→</span>}
                <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-200">
                  {step.tactic ?? "?"}
                  {step.technique && (
                    <span className="ml-1 font-mono text-[11px] text-indigo-300">
                      {step.technique}
                    </span>
                  )}
                  {step.finding_ref && (
                    <span className="ml-1 text-[11px] text-slate-500">{step.finding_ref}</span>
                  )}
                </span>
              </Fragment>
            ))}
          </div>
        </div>
      )}

      {incident.timeline && incident.timeline.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Timeline
          </p>
          <ul className="space-y-1 text-xs text-slate-300">
            {incident.timeline.map((t, i) => (
              <li key={i} className="flex flex-wrap gap-2">
                {t.time && <span className="font-mono text-slate-500">{t.time}</span>}
                <span>{t.event}</span>
                {t.finding_ref && <span className="text-slate-500">({t.finding_ref})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {refs.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-slate-500">Findings:</span>
          {refs.map((r) => (
            <span key={r} className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-indigo-300">
              {r}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function CorrelationRow({ entity }: { entity: CorrelationEntity }) {
  const [open, setOpen] = useState(false);
  return (
    <Fragment>
      <tr
        onClick={() => setOpen((o) => !o)}
        className={`cursor-pointer border-b border-slate-900 transition-colors hover:bg-slate-800/40 ${
          open ? "bg-slate-800/40" : ""
        }`}
      >
        <td className="px-3 py-2.5 font-mono text-xs text-indigo-300 break-all">{entity.value}</td>
        <td className="px-3 py-2.5">
          <EntityTypeBadge type={entity.entity_type} />
        </td>
        <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-300">
          {entity.dataset_count}
        </td>
        <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-300">
          {entity.finding_count}
        </td>
        <td className="px-3 py-2.5">
          <CategoryBadge category={entity.max_category} />
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="border-b border-slate-900 bg-slate-950/60 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Appears in
            </p>
            <ul className="space-y-1 text-sm text-slate-300">
              {entity.findings.map((f, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-indigo-300">{f.finding_ref}</span>
                  <span>{f.title}</span>
                  {f.category && <CategoryBadge category={f.category} />}
                  {f.dataset_name && (
                    <span className="text-xs text-slate-500">({f.dataset_name})</span>
                  )}
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

export default function CorrelationsPanel({
  tid,
  hid,
  reloadKey,
  hunt,
  onRefresh,
}: {
  tid: string;
  hid: string;
  reloadKey: number;
  hunt: Hunt | null;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [data, setData] = useState<CorrelationResult | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.getCorrelations(tid, hid), api.getIncidents(tid, hid)])
      .then(([corr, inc]) => {
        setData(corr);
        setIncidents(inc.incidents ?? []);
      })
      .catch((e: ApiError) => toast.error(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid, reloadKey]);

  const runCorrelation = async () => {
    setRunning(true);
    setJob({ id: "", status: "queued", progress: 0, current_task: "Starting correlation…" });
    try {
      const started = await api.runCorrelation(tid, hid);
      const done = await pollJob(tid, hid, String(started.id), setJob);
      if (done.status === "error") {
        toast.error(done.error ?? "Correlation failed");
      } else {
        const r = done.result as
          | { incidents?: number; merges?: number; enrichments?: number }
          | undefined;
        toast.success(
          `Correlation done — ${r?.incidents ?? 0} incident(s), ${r?.merges ?? 0} merged, ${r?.enrichments ?? 0} enriched`,
        );
        load();
      }
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setRunning(false);
    }
  };

  const toggleAuto = async () => {
    if (!hunt) return;
    try {
      await api.setAutoCorrelate(tid, hid, !hunt.auto_correlate);
      onRefresh();
    } catch (e) {
      toast.error((e as ApiError).message);
    }
  };

  const correlations = data?.correlations ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <PanelHeader
          title="Correlation phase"
          subtitle="Merges duplicates, enriches findings across datasets, and reconstructs attack-chains"
          right={
            <div className="flex items-center gap-3">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={!!hunt?.auto_correlate}
                  onChange={toggleAuto}
                  disabled={!hunt}
                  className="h-3.5 w-3.5 accent-indigo-500"
                />
                Auto-run after analysis
              </label>
              <Button onClick={runCorrelation} disabled={running}>
                {running ? <Spinner /> : "Run correlation"}
              </Button>
            </div>
          }
        />
        <div className="p-4">
          {(running || job) && (
            <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="text-slate-300">
                  {job?.status === "error"
                    ? "Correlation failed"
                    : job?.status === "cancelled"
                      ? "Cancelled"
                      : job?.current_task ?? "Starting…"}
                </span>
                <span className="font-mono text-slate-500">
                  {job?.progress != null ? `${Math.round(job.progress)}%` : ""}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
                <div
                  className="h-full bg-indigo-500 transition-all"
                  style={{ width: `${Math.max(3, job?.progress ?? 0)}%` }}
                />
              </div>
              {!!job?.log?.length && (
                <div className="mt-2 max-h-32 overflow-y-auto rounded bg-black/30 p-2 font-mono text-[11px] text-slate-400">
                  {job.log.map((l, i) => (
                    <div key={i}>
                      <span className="text-slate-600">{l.at.toFixed(1)}s</span> · {l.msg}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {incidents.length === 0 ? (
            <EmptyState>
              No correlated incidents yet. Run the correlation phase after analyzing
              datasets — it links findings that share entities into attack-chains.
            </EmptyState>
          ) : (
            <div className="space-y-3">
              {incidents.map((inc) => (
                <IncidentCard key={inc.id} incident={inc} />
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card>
        <PanelHeader
          title="Shared entities"
          subtitle="Entities appearing across multiple datasets — potential campaign signal"
          right={
            <div className="flex items-center gap-3">
              {data && (
                <span className="text-xs text-slate-500">
                  {correlations.length} correlated · {data.iocs.length} IOCs
                </span>
              )}
              <Button variant="ghost" onClick={load} disabled={loading}>
                {loading ? <Spinner /> : "Refresh"}
              </Button>
            </div>
          }
        />
        <div className="p-4">
          {data === null ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> Loading…
            </div>
          ) : correlations.length === 0 ? (
            <EmptyState>
              No cross-dataset correlations yet. They appear when the same host,
              user, IP, hash, or domain shows up in findings from two or more
              datasets.
            </EmptyState>
          ) : (
            <div className="overflow-hidden rounded border border-slate-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/40 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2 font-medium">Entity</th>
                    <th className="px-3 py-2 font-medium">Type</th>
                    <th className="px-3 py-2 text-center font-medium">Datasets</th>
                    <th className="px-3 py-2 text-center font-medium">Findings</th>
                    <th className="px-3 py-2 font-medium">Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {correlations.map((entity) => (
                    <CorrelationRow key={`${entity.entity_type}:${entity.value}`} entity={entity} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
