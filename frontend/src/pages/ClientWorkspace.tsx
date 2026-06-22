import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { Breadcrumbs } from "../components/Layout";
import { IconClients } from "../components/icons";
import { getModule, moduleClientBase } from "../lib/modules";
import { Badge, Spinner, Tabs } from "../components/ui";
import KnowledgePanel from "../components/KnowledgePanel";
import HuntsPanel from "../components/HuntsPanel";
import ClientOverview from "../components/client/ClientOverview";
import ClientContacts from "../components/client/ClientContacts";
import ClientCalendar from "../components/client/ClientCalendar";
import ClientEnvironment from "../components/client/ClientEnvironment";
import ClientSettings from "../components/client/ClientSettings";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "hunts", label: "Hunts" },
  { id: "knowledge", label: "Knowledge Base" },
  { id: "environment", label: "Environment" },
  { id: "contacts", label: "Contacts" },
  { id: "calendar", label: "Calendar" },
  { id: "settings", label: "Settings" },
];

function contractBadge(end?: string | null) {
  if (!end) return null;
  const days = Math.ceil((new Date(end).getTime() - Date.now()) / 86_400_000);
  if (Number.isNaN(days)) return null;
  if (days < 0)
    return <Badge className="border border-red-800 bg-red-950 text-red-300">Contract expired</Badge>;
  if (days <= 30)
    return <Badge className="border border-amber-800 bg-amber-950 text-amber-300">Expires in {days}d</Badge>;
  return <Badge className="border border-slate-700 bg-slate-800 text-slate-400">Contract ends {end}</Badge>;
}

export default function ClientWorkspace({ moduleId }: { moduleId?: string } = {}) {
  const { tid } = useParams<{ tid: string }>();
  const toast = useToast();
  const mod = moduleId ? getModule(moduleId) : undefined;
  const clientBase = mod ? moduleClientBase(mod) : "/clients";
  const [client, setClient] = useState<Tenant | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState(mod?.primaryTab ?? "overview");

  const load = () => {
    if (!tid) return;
    api
      .getTenant(tid)
      .then(setClient)
      .catch((e: ApiError) => {
        if (e.status === 404) setNotFound(true);
        else toast.error(e.message);
      });
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  if (!tid) return null;
  if (notFound) return <div className="text-slate-500">Client not found.</div>;

  const initials = (client?.name ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  const techTags = [client?.edr_platform, client?.siem_platform, client?.xdr_platform].filter(Boolean) as string[];
  const location = [client?.city, client?.country].filter(Boolean).join(", ");

  return (
    <div>
      <Breadcrumbs
        items={
          mod
            ? [{ label: mod.name, to: mod.path }, { label: client?.name ?? "…" }]
            : [{ label: "Clients", to: "/clients" }, { label: client?.name ?? "…" }]
        }
      />

      {/* Hero strip */}
      <div className="mb-6 flex flex-wrap items-start gap-4 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        {client?.logo_path ? (
          <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white p-1.5 ring-1 ring-slate-700">
            <img src={api.logoUrl(tid)} alt="" className="max-h-full max-w-full object-contain" />
          </div>
        ) : (
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-indigo-500/15 text-lg font-semibold text-indigo-200 ring-1 ring-inset ring-indigo-500/30">
            {initials || <IconClients width={22} height={22} />}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
              {client?.name ?? <Spinner />}
            </h1>
            {client && (
              <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">{client.slug}</span>
            )}
            {mod && (
              <Badge className="border border-indigo-700 bg-indigo-950 text-indigo-300">{mod.name}</Badge>
            )}
            {contractBadge(client?.contract_end)}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            {client?.sector && <span>{client.sector}</span>}
            {location && <span>· {location}</span>}
            {typeof client?.hunt_maturity === "number" && <span>· Maturity {client.hunt_maturity}/5</span>}
            {client?.sla_hours ? <span>· SLA {client.sla_hours}h</span> : null}
          </div>
          {techTags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {techTags.map((t) => (
                <span key={t} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{t}</span>
              ))}
            </div>
          )}
          {(client?.dpe_name || client?.pm_name) && (
            <p className="mt-2 text-xs text-slate-500">
              {client?.dpe_name && <>DPE: {client.dpe_name} </>}
              {client?.pm_name && <>· PM: {client.pm_name}</>}
            </p>
          )}
          <p className="mt-1 text-xs text-slate-600">Global client · available across all modules</p>
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && <ClientOverview tid={tid} clientBase={clientBase} />}
      {tab === "hunts" && <HuntsPanel tid={tid} clientBase={clientBase} />}
      {tab === "knowledge" && <KnowledgePanel tid={tid} />}
      {tab === "environment" && <ClientEnvironment tid={tid} />}
      {tab === "contacts" && <ClientContacts tid={tid} />}
      {tab === "calendar" && <ClientCalendar tid={tid} />}
      {tab === "settings" && client && <ClientSettings client={client} onUpdated={setClient} />}
    </div>
  );
}
