import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { Breadcrumbs } from "../components/Layout";
import { Card, Spinner } from "../components/ui";
import KnowledgePanel from "../components/KnowledgePanel";
import HuntsPanel from "../components/HuntsPanel";

export default function ClientWorkspace() {
  const { tid } = useParams<{ tid: string }>();
  const toast = useToast();
  const [client, setClient] = useState<Tenant | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!tid) return;
    api
      .getTenant(tid)
      .then(setClient)
      .catch((e: ApiError) => {
        if (e.status === 404) setNotFound(true);
        else toast.error(e.message);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  if (!tid) return null;
  if (notFound) return <div className="text-slate-500">Client not found.</div>;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Structured Hunts", to: "/structured-hunts" },
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "…" },
        ]}
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
          {client?.name ?? <Spinner />}
        </h1>
        {client && (
          <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
            {client.slug}
          </span>
        )}
      </div>

      {client?.context_notes && (
        <Card className="mb-6 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Client context</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">
            {client.context_notes}
          </p>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <KnowledgePanel tid={tid} />
        <HuntsPanel tid={tid} />
      </div>
    </div>
  );
}
