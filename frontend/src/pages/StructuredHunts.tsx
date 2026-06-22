import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { PageHeader, StatTile } from "../components/Layout";
import { getModule } from "../lib/modules";
import { IconPlus, IconStructured } from "../components/icons";
import ClientGrid from "../components/ClientGrid";
import { Button } from "../components/ui";

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
        basePath="/structured-hunts/clients"
        emptyHint="No clients yet. Create one to start a structured hunt."
      />
    </div>
  );
}
