import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import type { ClientOverview as Overview } from "../../lib/types";
import { useToast } from "../Toast";
import {
  Badge,
  Card,
  CategoryBadge,
  EmptyState,
  fmtDate,
  FindingStatusBadge,
  PanelHeader,
  Spinner,
} from "../ui";

const RISK_COLOR: Record<string, string> = {
  Critical: "text-red-300",
  High: "text-orange-300",
  Medium: "text-amber-300",
  Low: "text-emerald-300",
  None: "text-slate-400",
};

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  accent?: string;
}) {
  return (
    <Card className="px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${accent ?? "text-slate-100"}`}>{value}</p>
    </Card>
  );
}

export default function ClientOverview({ tid }: { tid: string }) {
  const toast = useToast();
  const [data, setData] = useState<Overview | null>(null);

  useEffect(() => {
    api
      .getClientOverview(tid)
      .then(setData)
      .catch((e: ApiError) => toast.error(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  if (!data)
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner /> Loading overview…
      </div>
    );

  const { counts, risk, by_category, recent_hunts, recent_findings } = data;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Tile label="Hunts" value={counts.hunts} />
        <Tile label="Datasets" value={counts.datasets} />
        <Tile label="Findings" value={counts.findings} />
        <Tile label="Validated" value={counts.validated} />
        <Tile
          label="Risk"
          value={
            <span className={RISK_COLOR[risk.label] ?? "text-slate-100"}>
              {risk.label}
              <span className="ml-1 text-sm text-slate-500">{risk.score}</span>
            </span>
          }
        />
      </div>

      {/* Category breakdown */}
      {by_category.length > 0 && (
        <Card>
          <PanelHeader title="Findings by category" />
          <div className="flex flex-wrap gap-2 p-4">
            {by_category.map((c) => (
              <span key={c.key} className="inline-flex items-center gap-1.5">
                <CategoryBadge category={c.key} />
                <span className="font-mono text-xs text-slate-400">{c.count}</span>
              </span>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent hunts */}
        <Card>
          <PanelHeader title="Recent hunts" subtitle="Latest hunt runs for this client" />
          <div className="p-2">
            {recent_hunts.length === 0 ? (
              <EmptyState>No hunts yet.</EmptyState>
            ) : (
              <ul className="divide-y divide-slate-800/70">
                {recent_hunts.map((h) => (
                  <li key={h.id}>
                    <Link
                      to={`/clients/${tid}/hunts/${h.id}`}
                      className="flex items-center justify-between gap-3 rounded px-2 py-2.5 hover:bg-slate-800/40"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-200">{h.name}</p>
                        <p className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-500">
                          {h.edr && <span>EDR: {h.edr}</span>}
                          {h.siem && <span>SIEM: {h.siem}</span>}
                          <span>{fmtDate(h.created_at ?? undefined)}</span>
                        </p>
                      </div>
                      <Badge className="shrink-0 border border-slate-700 bg-slate-800 text-slate-300">
                        {h.status}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        {/* Recent findings */}
        <Card>
          <PanelHeader title="Recent findings" subtitle="Across all hunts for this client" />
          <div className="p-2">
            {recent_findings.length === 0 ? (
              <EmptyState>No findings yet.</EmptyState>
            ) : (
              <ul className="divide-y divide-slate-800/70">
                {recent_findings.map((f) => (
                  <li key={f.id}>
                    <Link
                      to={`/clients/${tid}/hunts/${f.hunt_id}`}
                      className="flex items-center justify-between gap-3 rounded px-2 py-2.5 hover:bg-slate-800/40"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm text-slate-200">
                          <span className="font-mono text-xs text-indigo-300">
                            {f.finding_ref}
                          </span>{" "}
                          {f.title}
                        </p>
                        <div className="mt-1 flex items-center gap-2">
                          <CategoryBadge category={f.category} />
                          {f.severity && (
                            <span className="text-xs text-slate-500">{f.severity}</span>
                          )}
                        </div>
                      </div>
                      <FindingStatusBadge status={f.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
