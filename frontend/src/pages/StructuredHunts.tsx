import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { PageHeader, StatTile } from "../components/Layout";
import { getModule } from "../lib/modules";
import { IconPlus, IconStructured } from "../components/icons";
import ClientGrid from "../components/ClientGrid";
import { Button, Card } from "../components/ui";

const MODULE = getModule("structured-hunts")!;

export default function StructuredHunts() {
  const toast = useToast();
  const [clients, setClients] = useState<Tenant[] | null>(null);

  useEffect(() => {
    api
      .listTenants()
      .then(setClients)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setClients([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <PageHeader
        icon={<IconStructured width={22} height={22} />}
        title="Structured Hunts"
        description={MODULE.description}
        actions={
          <Link to="/clients">
            <Button variant="primary">
              <IconPlus width={16} height={16} /> New Client
            </Button>
          </Link>
        }
      />

      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Clients" value={clients?.length ?? "—"} hint="Global workspaces" />
        <StatTile label="Pipeline" value="3-stage" hint="Analyst → Reviewer → QA" />
        <StatTile label="Evidence" value="Strict" hint="No fabrication" />
        <StatTile label="Deployment" value="Local" hint="On-box Ollama" />
      </div>

      <Card className="mb-8 border-indigo-500/20 bg-indigo-500/[0.03] p-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-indigo-300/80">
          How it works
        </p>
        <ol className="grid grid-cols-1 gap-2 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-3">
          {[
            "Pick a client & start a hunt (language, EDR/SIEM, methodology).",
            "The engine comprehends the methodology before any data.",
            "Upload CSV result sets and analyze them one at a time.",
            "Review evidence-only findings; validate to teach the KB.",
            "Correlate entities across datasets for campaign signal.",
            "Generate a bilingual, client-ready DOCX report.",
          ].map((step, i) => (
            <li key={i} className="flex gap-2">
              <span className="font-mono text-xs text-indigo-400">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </Card>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Clients
        </h2>
        <Link to="/clients" className="text-xs text-indigo-400 hover:text-indigo-300">
          Manage clients →
        </Link>
      </div>
      <ClientGrid
        clients={clients}
        emptyHint="No clients yet. Create one to start a structured hunt."
      />
    </div>
  );
}
