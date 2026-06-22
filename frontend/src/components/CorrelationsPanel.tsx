import { Fragment, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { CorrelationEntity, CorrelationResult } from "../lib/types";
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

function EntityTypeBadge({ type }: { type: string }) {
  return (
    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide text-slate-300">
      {ENTITY_LABEL[type] ?? type}
    </span>
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
        <td className="px-3 py-2.5 font-mono text-xs text-indigo-300 break-all">
          {entity.value}
        </td>
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
                  <span className="font-mono text-xs text-indigo-300">
                    {f.finding_ref}
                  </span>
                  <span>{f.title}</span>
                  {f.category && <CategoryBadge category={f.category} />}
                  {f.dataset_name && (
                    <span className="text-xs text-slate-500">
                      ({f.dataset_name})
                    </span>
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
}: {
  tid: string;
  hid: string;
  reloadKey: number;
}) {
  const toast = useToast();
  const [data, setData] = useState<CorrelationResult | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .getCorrelations(tid, hid)
      .then(setData)
      .catch((e: ApiError) => toast.error(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid, reloadKey]);

  const correlations = data?.correlations ?? [];

  return (
    <Card>
      <PanelHeader
        title="Correlations"
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
  );
}
