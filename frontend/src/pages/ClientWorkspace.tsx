import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { Breadcrumbs } from "../components/Layout";
import { IconClients } from "../components/icons";
import { Spinner, Tabs } from "../components/ui";
import KnowledgePanel from "../components/KnowledgePanel";
import HuntsPanel from "../components/HuntsPanel";
import ClientOverview from "../components/client/ClientOverview";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "hunts", label: "Hunts" },
  { id: "knowledge", label: "Knowledge Base" },
];

export default function ClientWorkspace() {
  const { tid } = useParams<{ tid: string }>();
  const toast = useToast();
  const [client, setClient] = useState<Tenant | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState("overview");

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

  const initials = (client?.name ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Structured Hunts", to: "/structured-hunts" },
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "…" },
        ]}
      />

      {/* Hero strip */}
      <div className="mb-6 flex flex-wrap items-start gap-4 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-indigo-500/15 text-lg font-semibold text-indigo-200 ring-1 ring-inset ring-indigo-500/30">
          {initials || <IconClients width={22} height={22} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
              {client?.name ?? <Spinner />}
            </h1>
            {client && (
              <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                {client.slug}
              </span>
            )}
          </div>
          {client?.context_notes ? (
            <p className="mt-1.5 line-clamp-2 max-w-3xl text-sm text-slate-400">
              {client.context_notes}
            </p>
          ) : (
            <p className="mt-1.5 text-sm text-slate-600 italic">No context notes</p>
          )}
          <p className="mt-1 text-xs text-slate-600">
            Global client · available across all modules
          </p>
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && <ClientOverview tid={tid} />}
      {tab === "hunts" && <HuntsPanel tid={tid} />}
      {tab === "knowledge" && <KnowledgePanel tid={tid} />}
    </div>
  );
}
