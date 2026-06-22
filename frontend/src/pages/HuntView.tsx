import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Hunt, Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { Breadcrumbs } from "../components/Layout";
import { Badge, Card, Spinner } from "../components/ui";
import DatasetsPanel from "../components/DatasetsPanel";
import FindingsPanel from "../components/FindingsPanel";

export default function HuntView() {
  const { tid, hid } = useParams<{ tid: string; hid: string }>();
  const toast = useToast();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [hunt, setHunt] = useState<Hunt | null>(null);
  // Bumping this key tells the FindingsPanel to reload (after an analysis run).
  const [findingsKey, setFindingsKey] = useState(0);

  useEffect(() => {
    if (!tid || !hid) return;
    api.getTenant(tid).then(setTenant).catch(() => undefined);
    api
      .getHunt(tid, hid)
      .then(setHunt)
      .catch((e: ApiError) => toast.error(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid]);

  if (!tid || !hid) return null;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Tenants", to: "/" },
          { label: tenant?.name ?? "…", to: `/tenants/${tid}` },
          { label: hunt?.name ?? "…" },
        ]}
      />

      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-slate-100">
            {hunt?.name ?? <Spinner />}
          </h1>
          {hunt && (
            <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
              {hunt.status}
            </Badge>
          )}
        </div>
        {hunt?.objective && (
          <p className="mt-2 max-w-3xl text-sm text-slate-400">{hunt.objective}</p>
        )}
      </div>

      {hunt?.methodology_text && (
        <Card className="mb-6 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">
            Methodology override
          </p>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-xs text-slate-300">
            {hunt.methodology_text}
          </pre>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6">
        <DatasetsPanel
          tid={tid}
          hid={hid}
          onAnalysisComplete={() => setFindingsKey((k) => k + 1)}
        />
        <FindingsPanel tid={tid} hid={hid} reloadKey={findingsKey} />
      </div>
    </div>
  );
}
